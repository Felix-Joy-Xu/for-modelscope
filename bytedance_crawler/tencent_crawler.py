import asyncio
import json
import time
import random
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from urllib.parse import urlencode

from playwright.async_api import async_playwright
from models import JobRecord, Metadata, BasicInfo, Requirements
from storage import Storage

def _append_jsonl(path: Path, record: JobRecord) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")

async def crawl_experienced(track: str, output_dir: Path, db_path: Path, limit: int, headed: bool) -> int:
    yielded = 0
    seen_ids: set[str] = set()
    out_file = output_dir / f"jobs_tencent_{track}.jsonl"
    storage = Storage(db_path)
    
    print(f"\n{'='*60}")
    print(f"  [Tencent Crawler] track={track}")
    print(f"  target: {'ALL' if limit == 0 else f'{limit}'}")
    print(f"  output: {out_file}")
    print(f"  db_existing: {storage.count(track)}")
    print(f"{'='*60}\n")

    api_base = "https://careers.tencent.com/tencentcareer/api/post/Query"
    page_size = 50
    page_index = 1
    
    print("[1/2] Connecting to Tencent public APIs...")
    async with async_playwright() as p:
        # Use playwright request context just for connection pooling and user agent
        req_ctx = await p.request.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        
        try:
            print("[2/2] Start querying API...")
            while True:
                if limit > 0 and yielded >= limit:
                    break
                    
                timestamp = int(time.time() * 1000)
                params = {
                    "timestamp": str(timestamp),
                    "pageSize": str(page_size),
                    "pageIndex": str(page_index),
                    "language": "zh-cn",
                    "area": "cn"
                }
                
                url = f"{api_base}?{urlencode(params)}"
                resp = await req_ctx.get(url, timeout=30_000)
                
                if not resp.ok:
                    print(f"  [API ERROR] status_code={resp.status}")
                    break
                    
                data = await resp.json()
                if int(data.get("Code", 0)) != 200:
                    print(f"  [API FAIL] msg={data.get('Data', 'Unknown Error')}")
                    break
                    
                posts = data.get("Data", {}).get("Posts")
                if not posts or not isinstance(posts, list):
                    print(f"\n[DONE] No more data on page {page_index}, ending.")
                    break
                    
                page_new = 0
                for post in posts:
                    if limit > 0 and yielded >= limit:
                        break
                        
                    raw_id = post.get("PostId")
                    job_id = str(raw_id).strip() if raw_id else ""
                    if not job_id: continue
                    
                    if job_id in seen_ids or storage.has("tencent", track, job_id):
                        continue
                        
                    seen_ids.add(job_id)
                    title = str(post.get("RecruitPostName") or "").strip() or job_id
                    loc = str(post.get("LocationName") or "").strip()
                    bg = str(post.get("BGName") or "").strip()
                    cat = str(post.get("CategoryName") or "").strip()
                    desc = str(post.get("Responsibility") or "").strip()
                    req = str(post.get("Requirement") or str(post.get("RequireWorkYearsName") or "")).strip()
                    purl = str(post.get("PostURL") or "").strip() or f"http://careers.tencent.com/jobdesc.html?postId={job_id}"
                    
                    cats = [x for x in [bg, cat] if x]
                    
                    record = JobRecord(
                        metadata=Metadata(platform="tencent", track=track, crawl_timestamp=datetime.now(timezone.utc).isoformat(), job_id=job_id, url=purl),
                        basic_info=BasicInfo(job_title=title, category_path=cats, location=[loc] if loc else [], publish_date=str(post.get("LastUpdateTime") or "")),
                        requirements=Requirements(description=desc, requirement=req, raw_jd_text=f"{desc}\n{req}".strip()),
                    )
                    
                    storage.save(track, job_id, record.metadata.url, record.model_dump())
                    _append_jsonl(out_file, record)
                    yielded += 1
                    page_new += 1
                
                print(f"  [PAGE] {page_index:>3}  total={len(posts)}  new={page_new}  cumulative={yielded}")
                
                if len(posts) < page_size:
                    print(f"\n[DONE] Fetched last page, ending.")
                    break
                    
                page_index += 1
                await asyncio.sleep(random.uniform(0.3, 0.8))
                
            print(f"\n[2/2] Crawling complete!")
            print(f"  new_records: {yielded}")
            print(f"  db_total: {storage.count(track)}")
            print(f"  output: {out_file}")
            
        except Exception as e:
            print(f"  [FATAL] {type(e).__name__}: {e}")
            
        finally:
            storage.close()
            await req_ctx.dispose()
            
    return yielded

async def crawl_campus_intern(track: str, output_dir: Path, db_path: Path, limit: int, headed: bool) -> int:
    yielded = 0
    seen_ids: set[str] = set()
    out_file = output_dir / f"jobs_tencent_{track}.jsonl"
    storage = Storage(db_path)
    
    # Mapping for join.qq.com
    project_mapping = {
        "campus": [1], # 校园招聘
        "intern": [2]  # 实习生招聘
    }
    mapping_ids = project_mapping.get(track, [1])
    
    print(f"\n{'='*60}")
    print(f"  [Tencent Crawler] track={track}")
    print(f"  target: {'ALL' if limit == 0 else f'{limit}'}")
    print(f"  output: {out_file}")
    print(f"  db_existing: {storage.count(track)}")
    print(f"{'='*60}\n")

    search_api = "https://join.qq.com/api/v1/position/searchPosition"
    detail_api = "https://join.qq.com/api/v1/post/getPostDetail"
    page_size = 20
    page_index = 1
    
    async with async_playwright() as p:
        req_ctx = await p.request.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            extra_http_headers={"Referer": f"https://join.qq.com/post.html?query=p_{mapping_ids[0]}"}
        )
        
        try:
            print(f"[1/2] Fetching {track} list...")
            while True:
                if limit > 0 and yielded >= limit:
                    break
                    
                timestamp = int(time.time() * 1000)
                url = f"{search_api}?timestamp={timestamp}"
                
                payload = {
                    "projectIdList": [],
                    "projectMappingIdList": mapping_ids,
                    "keyword": "",
                    "bgList": [],
                    "workCountryType": 0,
                    "workCityList": [],
                    "recruitCityList": [],
                    "positionFidList": [],
                    "pageIndex": page_index,
                    "pageSize": page_size
                }
                
                resp = await req_ctx.post(url, data=json.dumps(payload), headers={"Content-Type": "application/json;charset=UTF-8"}, timeout=30_000)
                if not resp.ok:
                    print(f"  [API ERROR] Search fail status={resp.status}")
                    break
                    
                data = await resp.json()
                pos_list = (data.get("data") or {}).get("positionList", [])
                if not pos_list:
                    print(f"\n[DONE] No more data on page {page_index}, ending.")
                    break
                    
                page_new = 0
                for post in pos_list:
                    if limit > 0 and yielded >= limit:
                        break
                        
                    raw_id = post.get("postId") or post.get("id")
                    job_id = str(raw_id).strip() if raw_id else ""
                    if not job_id: continue
                    
                    if job_id in seen_ids or storage.has("tencent", track, job_id):
                        continue
                        
                    seen_ids.add(job_id)
                    
                    # Fetch details
                    timestamp = int(time.time() * 1000)
                    detail_url = f"{detail_api}?timestamp={timestamp}&postId={job_id}"
                    d_resp = await req_ctx.get(detail_url, timeout=30_000)
                    
                    desc, req = "", ""
                    if d_resp.ok:
                        d_data = await d_resp.json()
                        d_info = d_data.get("data", {}) or {}
                        desc = str(d_info.get("responsibility") or "").strip()
                        req = str(d_info.get("requirement") or "").strip()
                    
                    title = str(post.get("positionTitle") or post.get("position") or "").strip() or job_id
                    locs = post.get("workCities") or []
                    if isinstance(locs, str):
                        locs = [x.strip() for x in locs.split("/") if x.strip()]
                    elif not isinstance(locs, list):
                        locs = []
                        
                    bgs = post.get("bgs") or ""
                    bg_list = [x.strip() for x in bgs.split("/") if x.strip()] if isinstance(bgs, str) else []
                    
                    cat = str(post.get("projectName") or post.get("recruitLabelName") or "").strip()
                    cats = [x for x in bg_list + [cat] if x]
                    
                    purl = f"https://join.qq.com/detail.html?id={job_id}"
                    
                    record = JobRecord(
                        metadata=Metadata(platform="tencent", track=track, crawl_timestamp=datetime.now(timezone.utc).isoformat(), job_id=job_id, url=purl),
                        basic_info=BasicInfo(job_title=title, category_path=cats, location=locs, publish_date=None),
                        requirements=Requirements(description=desc, requirement=req, raw_jd_text=f"{desc}\n{req}".strip()),
                    )
                    
                    storage.save(track, job_id, record.metadata.url, record.model_dump())
                    _append_jsonl(out_file, record)
                    yielded += 1
                    page_new += 1
                    
                    # Tiny delay between details to avoid rate limit
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                
                print(f"  [PAGE] {page_index:>3}  total={len(pos_list)}  new={page_new}  cumulative={yielded}")
                
                if len(pos_list) < page_size:
                    break
                    
                page_index += 1
                await asyncio.sleep(random.uniform(0.5, 1.2))
                
            print(f"\n[DONE] Crawling {track} complete!")
            print(f"  new_records: {yielded}")
            
        except Exception as e:
            print(f"  [FATAL] {type(e).__name__}: {e}")
        finally:
            storage.close()
            await req_ctx.dispose()
            
    return yielded

async def crawl(track: str, output_dir: Path, db_path: Path, *, limit: int = 0, headed: bool = True) -> int:
    if track == "experienced":
        return await crawl_experienced(track, output_dir, db_path, limit=limit, headed=headed)
    elif track in ("campus", "intern"):
        return await crawl_campus_intern(track, output_dir, db_path, limit=limit, headed=headed)
    else:
        raise ValueError(f"不支持的 track: {track}")
