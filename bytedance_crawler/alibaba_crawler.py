"""阿里巴巴招聘爬虫核心逻辑.

- 社招 (experienced): 通过 fc.alibaba.com 动态提取子站，拦截网络请求并启发式提取数据。
- 校招/实习 (campus/intern): 通过 campus-talent.alibaba.com 统一请求。
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page, async_playwright

from models import BasicInfo, JobRecord, Metadata, Requirements
from storage import Storage

def _append_jsonl(path: Path, record: JobRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json(ensure_ascii=False))
        f.write("\n")

def _category_path(item: dict[str, Any]) -> list[str]:
    out: list[str] = []
    def add(v: Any) -> None:
        if isinstance(v, str):
            s = v.strip()
            if s and s not in out:
                out.append(s)

    for k in (
        "categoryName", "category", "positionType", "positionTypeName",
        "jobCategory", "jobCategoryName", "job_category_name", "department",
        "departmentName", "orgName", "organization", "groupName", "bgName",
        "businessUnit", "business", "categoryType"
    ):
        add(item.get(k))

    for k in ("circleNames", "orgPath", "category_path"):
        v = item.get(k)
        if isinstance(v, list):
            for x in v[:6]:
                add(x)

    if len(out) < 2:
        for k, v in item.items():
            lk = str(k).lower()
            if isinstance(v, str) and any(x in lk for x in ("category", "dept", "department", "org", "bg", "group", "business")):
                add(v)
            if len(out) >= 3:
                break
    return out

def _looks_like_job_list(payload: Any) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    def walk(x: Any) -> None:
        if isinstance(x, dict):
            title = str(x.get("name") or x.get("title") or x.get("positionName") or "").strip()
            if title and title not in {"标题", "介绍", "介绍文案", "title", "undefined"}:
                raw_id = x.get("id") or x.get("positionId") or x.get("jobId")
                job_id = str(raw_id).strip() if raw_id is not None else ""
                has_id = bool(job_id) and (job_id.isdigit() or len(job_id) >= 8)

                desc = str(x.get("description") or x.get("jobDescription") or "").strip()
                req = str(x.get("requirement") or x.get("jobRequirement") or "").strip()
                jd = "\n".join([p for p in [desc, req] if p]).strip()
                jd_ok = len(jd) >= 120

                if has_id and jd_ok:
                    jobs.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for it in x:
                walk(it)
    walk(payload)
    return jobs

def _iter_links(obj: Any) -> list[str]:
    out: list[str] = []
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == "link" and isinstance(v, str) and v.startswith("http"):
                    out.append(v)
                else:
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq

async def _get_talent_csrf(page: Page) -> str | None:
    try:
        cookies = await page.context.cookies()
        for c in cookies:
            if c.get("name") == "_csrf" and c.get("value"):
                return str(c["value"])
    except Exception:
        pass
    return None

async def crawl_campus(track: str, output_dir: Path, db_path: Path, limit: int, headed: bool) -> int:
    yielded = 0
    seen_ids: set[str] = set()
    
    out_file = output_dir / f"jobs_alibaba_{track}.jsonl"
    storage = Storage(db_path)
    
    print(f"\n{'='*60}")
    print(f"  [Alibaba Crawler] track={track}")
    print(f"  target: {'ALL' if limit == 0 else f'{limit}'}")
    print(f"  output: {out_file}")
    print(f"  db_existing: {storage.count(track)}")
    print(f"{'='*60}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        page = await browser.new_page()
        
        try:
            home = "https://campus-talent.alibaba.com/campus/position"
            print("[1/3] Fetching initial CSRF token...")
            await page.goto(home, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2000)
            
            csrf = await _get_talent_csrf(page)
            if not csrf:
                try:
                    async with page.expect_response(lambda r: "/position/search" in (r.url or ""), timeout=15_000) as info:
                        await page.goto(f"{home}?batchId=100000540002", wait_until="domcontentloaded", timeout=60_000)
                    r = await info.value
                    q = parse_qs(urlparse(r.url).query)
                    if q.get("_csrf"): csrf = str(q["_csrf"][0])
                except Exception:
                    pass
            if not csrf:
                raise RuntimeError("Failed to obtain Alibaba _csrf cookie")
            
            api = f"https://campus-talent.alibaba.com/position/search?_csrf={csrf}"
            batch_id = 100000540002  # General campus/internship batch id as fallback
            
            # 监听尝试直接拿到真实的 batch ID
            try:
                async with page.expect_response(lambda r: "/searchCondition/listBatch" in (r.url or ""), timeout=15_000) as info:
                    await page.goto(home, wait_until="domcontentloaded")
                r = await info.value
                b = await r.json()
                content = b.get("content")
                for key in ("internship", "graduate"):
                    arr = (content or {}).get(key)
                    if isinstance(arr, list) and arr and isinstance(arr[0].get("id"), int):
                        batch_id = int(arr[0]["id"])
                        break
            except Exception:
                pass
                
            print("[2/3] Start querying API...")
            page_index = 1
            page_size = 20
            
            while True:
                if limit > 0 and yielded >= limit:
                    print(f"\n[OK] Reached limit={limit}, stopping.")
                    break
                    
                payload = {
                    "batchId": batch_id,
                    "pageIndex": page_index,
                    "pageSize": page_size,
                    "channel": "campus_group_official_site",
                    "language": "zh",
                }
                
                resp = await page.request.post(
                    api, 
                    data=json.dumps(payload, ensure_ascii=False),
                    headers={"content-type": "application/json"},
                    timeout=20_000
                )
                data = await resp.json()
                datas = ((data.get("content") or {}).get("datas") or [])
                if not isinstance(datas, list) or not datas:
                    print(f"\n[DONE] No more data on page {page_index}, ending.")
                    break
                    
                page_new = 0
                for item in datas:
                    if limit > 0 and yielded >= limit:
                        break
                    if not isinstance(item, dict): continue
                    
                    job_id = str(item.get("id")).strip()
                    if not job_id or job_id in seen_ids or storage.has("alibaba", track, job_id):
                        continue
                        
                    seen_ids.add(job_id)
                    title = str(item.get("name") or "").strip() or job_id
                    locs = item.get("workLocations")
                    locations = [str(x).strip() for x in locs] if isinstance(locs, list) else []
                    
                    desc = str(item.get("description") or "").strip()
                    req = str(item.get("requirement") or "").strip()
                    url = str(item.get("positionUrl") or "").strip() or f"{home}?positionId={job_id}"
                    
                    record = JobRecord(
                        metadata=Metadata(platform="alibaba", track=track, crawl_timestamp=datetime.now(timezone.utc).isoformat(), job_id=job_id, url=url),
                        basic_info=BasicInfo(job_title=title, category_path=_category_path(item), location=locations, publish_date=None),
                        requirements=Requirements(description=desc, requirement=req, raw_jd_text="\n".join([p for p in [desc, req] if p]).strip()),
                    )
                    
                    storage.save("alibaba", track, job_id, record.metadata.url, record.model_dump())
                    _append_jsonl(out_file, record)
                    yielded += 1
                    page_new += 1
                    
                print(f"  [PAGE] {page_index:>3}  total={len(datas)}  new={page_new}  cumulative={yielded}")
                page_index += 1
                await page.wait_for_timeout(random.randint(800, 2000))
                
            print(f"\n[3/3] Crawling complete!")
            print(f"  new_records: {yielded}")
            print(f"  db_total: {storage.count('alibaba', track)}")
            print(f"  output: {out_file}")
            
        finally:
            storage.close()
            await browser.close()
            
    return yielded

async def crawl_experienced(track: str, output_dir: Path, db_path: Path, limit: int, headed: bool) -> int:
    yielded = 0
    seen_ids: set[str] = set()
    out_file = output_dir / f"jobs_alibaba_{track}.jsonl"
    storage = Storage(db_path)
    
    print(f"\n{'='*60}")
    print(f"  [Alibaba Crawler] track={track}")
    print(f"  target: {'ALL' if limit == 0 else f'{limit}'}")
    print(f"  output: {out_file}")
    print(f"  db_existing: {storage.count(track)}")
    print(f"{'='*60}\n")
    
    home_cfg = "https://fc.alibaba.com/0.0.7/default/recruit-page-home.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        page = await browser.new_page()
        try:
            print("[1/3] Fetching subsidiary definitions...")
            cfg_resp = await page.request.get(home_cfg, timeout=30_000)
            cfg = await cfg_resp.json()
            links = _iter_links(cfg)
            all_subsidiaries = [u for u in links if u.startswith("http")]
            subs_seen = set()
            subsidiaries = []
            for u in all_subsidiaries:
                base = u.split("?")[0].rstrip("/")
                if base not in subs_seen:
                    subs_seen.add(base)
                    subsidiaries.append(u)
            
            if not subsidiaries:
                raise RuntimeError("Failed to extract target priority subsidiary URLs.")
            print(f"  Found {len(subsidiaries)} priority ITC/Holding recruitment portals.")
            
            # Establishing talent cookie
            try:
                await page.goto("https://talent.alibaba.com/?lang=zh", wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(1000)
            except Exception: pass
            
            print("[2/3] Visiting subsidiaries & crawling...")
            
            for idx, url in enumerate(subsidiaries):
                if limit > 0 and yielded >= limit:
                    break
                
                print(f"  -> [{idx+1}/{len(subsidiaries)}] {url}")
                page = await browser.new_page()
                try:
                    # Construct targeting URL
                    base = url.split("?")[0].rstrip("/")
                    home_url = f"{base}/off-campus/position-list?lang=zh"
                    
                    # Intercept the API and CSRF
                    api_url = ""
                    csrf = ""
                    async with page.expect_response(lambda r: "search?_csrf=" in r.url, timeout=20_000) as resp_info:
                        await page.goto(home_url, wait_until="domcontentloaded", timeout=40_000)
                        
                    resp = await resp_info.value
                    api_url = resp.url
                    q = parse_qs(urlparse(api_url).query)
                    if q.get("_csrf"): csrf = str(q["_csrf"][0])
                    
                    if not api_url or not csrf:
                        print(f"     [WARN] Could not intercept Shuzi API.")
                        continue
                        
                    # Now paginate directly via POST
                    page_index = 1
                    page_size = 20
                    subsite_new = 0
                    
                    while True:
                        if limit > 0 and yielded >= limit: break
                        payload = {"channel":"group_official_site","language":"zh","batchId":"","categories":"","deptCodes":[],"key":"","pageIndex":page_index,"pageSize":page_size,"regions":"","subCategories":"","shareType":"","shareId":"","myReferralShareCode":""}
                        
                        r = await page.request.post(
                            api_url,
                            data=json.dumps(payload, ensure_ascii=False),
                            headers={"content-type": "application/json"},
                            timeout=20_000
                        )
                        data = await r.json()
                        datas = ((data.get("content") or {}).get("datas") or [])
                        if not isinstance(datas, list) or not datas:
                            break
                            
                        page_new = 0
                        for jd in datas:
                            if limit > 0 and yielded >= limit: break
                            if not isinstance(jd, dict): continue
                            
                            raw_id = jd.get("id") or jd.get("positionId") or jd.get("jobId")
                            job_id = str(raw_id).strip() if raw_id is not None else ""
                            if not job_id: continue
                            if job_id in seen_ids or storage.has("alibaba", track, job_id): continue
                                
                            seen_ids.add(job_id)
                            title = str(jd.get("name") or jd.get("title") or "").strip() or job_id
                            locs = jd.get("workLocations") or jd.get("workLocation") or jd.get("location")
                            locations = [str(x).strip() for x in locs if str(x).strip()] if isinstance(locs, list) else ([str(locs).strip()] if isinstance(locs, str) and locs.strip() else [])
                            
                            desc = str(jd.get("description") or jd.get("jobDescription") or "").strip()
                            req = str(jd.get("requirement") or jd.get("jobRequirement") or "").strip()
                            purl = str(jd.get("positionUrl") or jd.get("url") or "").strip() or url
                            if purl.startswith("/"): purl = base + purl
                                
                            record = JobRecord(
                                metadata=Metadata(platform="alibaba", track=track, crawl_timestamp=datetime.now(timezone.utc).isoformat(), job_id=job_id, url=purl),
                                basic_info=BasicInfo(job_title=title, category_path=_category_path(jd), location=locations, publish_date=None),
                                requirements=Requirements(description=desc, requirement=req, raw_jd_text="\n".join([p for p in [desc, req] if p]).strip()),
                            )
                            storage.save("alibaba", track, job_id, record.metadata.url, record.model_dump())
                            _append_jsonl(out_file, record)
                            yielded += 1
                            page_new += 1
                            subsite_new += 1
                            
                        print(f"     [PAGE] {page_index:>3}  total={len(datas)}  new={page_new}")
                        if len(datas) < page_size:
                            break
                        page_index += 1
                        await page.wait_for_timeout(random.randint(800, 2000))
                        
                    if subsite_new > 0:
                        print(f"     [+] Extracted {subsite_new} jobs from this subsidiary.")
                        
                except Exception as e:
                    print(f"     [WARN] navigation/API failed: {type(e).__name__}")
                finally:
                    try: await page.close()
                    except Exception: pass
                    
            print(f"\n[3/3] Crawling complete!")
            print(f"  new_records: {yielded}")
            print(f"  db_total: {storage.count('alibaba', track)}")
            print(f"  output: {out_file}")

        finally:
            storage.close()
            await browser.close()
            
    return yielded

async def crawl(track: str, output_dir: Path, db_path: Path, *, limit: int = 0, headed: bool = True) -> int:
    if track == "experienced":
        return await crawl_experienced(track, output_dir, db_path, limit=limit, headed=headed)
    elif track in ("campus", "intern"):
        return await crawl_campus(track, output_dir, db_path, limit=limit, headed=headed)
    else:
        raise ValueError(f"不支持的 track: {track}")
