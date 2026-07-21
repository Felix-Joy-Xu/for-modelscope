"""美团招聘爬虫核心逻辑 - 拦截增强版.

策略：使用 Playwright 拦截浏览器请求来捕获招聘数据。
该方案最稳健，因为它直接利用了网站自身的认证和防爬机制。
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Response

from models import BasicInfo, JobRecord, Metadata, Requirements
from storage import Storage

# ──────────────────────── 配置 ────────────────────────

API_MATCH = "/api/official/job/getJobList"
SELECTOR_NEXT = "li.mtd-pagination-next"
CLASS_DISABLED = "mtd-pagination-item-disabled"

TRACK_MAPPING = {
    "experienced": "https://zhaopin.meituan.com/web/social",
    "campus":      "https://zhaopin.meituan.com/web/campus",
    "intern":      "https://zhaopin.meituan.com/web/campus",
}

# ──────────────────────── 数据解析 ────────────────────────

def _parse_ms_date(ms: int | None) -> str | None:
    if not ms:
        return None
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return dt.date().isoformat()
    except Exception:
        return None

def _parse_job(item: dict[str, Any], track: str) -> JobRecord | None:
    job_id = str(item.get("jobUnionId") or "").strip()
    if not job_id:
        return None

    title = str(item.get("name") or "").strip() or job_id
    
    locations: list[str] = []
    city_list = item.get("cityList")
    if isinstance(city_list, list):
        for c in city_list:
            if isinstance(c, dict):
                name = str(c.get("name") or "").strip()
                if name: locations.append(name)
    
    cats: list[str] = []
    for k in ("bgName", "jobCategoryName", "jobFamily", "jobFamilyGroup"):
        v = str(item.get(k) or "").strip()
        if v and v not in cats:
            cats.append(v)

    desc = str(item.get("jobDuty") or "").strip()
    req = str(item.get("jobRequirement") or "").strip()
    raw_jd = f"{desc}\n{req}".strip()

    pub_date = _parse_ms_date(item.get("refreshTime"))
    url = f"https://zhaopin.meituan.com/web/job/{job_id}"

    return JobRecord(
        metadata=Metadata(
            platform="meituan",
            track=track,
            crawl_timestamp=datetime.now(timezone.utc).isoformat(),
            job_id=job_id,
            url=url,
        ),
        basic_info=BasicInfo(
            job_title=title,
            category_path=cats,
            location=locations,
            publish_date=pub_date,
        ),
        requirements=Requirements(
            description=desc,
            requirement=req,
            raw_jd_text=raw_jd,
        ),
    )

def _append_jsonl(path: Path, record: JobRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json(ensure_ascii=False))
        f.write("\n")

# ──────────────────────── 核心爬取 ────────────────────────

async def crawl(
    track: str,
    output_dir: Path,
    db_path: Path,
    *,
    limit: int = 0,
    headed: bool = True,
) -> int:
    start_url = TRACK_MAPPING.get(track)
    if not start_url:
        raise ValueError(f"不支持的 track: {track}")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"jobs_meituan_{track}.jsonl"
    storage = Storage(db_path)

    print(f"\n{'='*60}")
    print(f"  [Meituan Interceptor] track={track}")
    print(f"  target: {'ALL' if limit == 0 else f'{limit}'}")
    print(f"  output: {out_file}")
    print(f"  db_existing: {storage.count('meituan', track)}")
    print(f"{'='*60}\n")

    yielded = 0
    seen_ids: set[str] = set()
    response_queue: asyncio.Queue[dict] = asyncio.Queue()

    async def handle_response(response: Response):
        if API_MATCH in response.url and response.request.method == "POST":
            # 只有响应成功且是 JSON 时放入队列
            if response.status == 200:
                try:
                    data = await response.json()
                    if "data" in data and "list" in data["data"]:
                        await response_queue.put(data)
                except Exception:
                    pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.on("response", handle_response)
        
        try:
            print(f"[1/2] Loading {start_url}...")
            await page.goto(start_url, wait_until="networkidle")
            
            page_no = 1
            while True:
                # 等待队列中的响应数据
                try:
                    data = await asyncio.wait_for(response_queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    print(f"  [WARN] Page {page_no} data timeout. ending.")
                    break

                job_list = data["data"]["list"]
                if not job_list:
                    print(f"  [DONE] Empty list on page {page_no}.")
                    break

                page_new = 0
                for item in job_list:
                    if limit > 0 and yielded >= limit:
                        break
                    
                    record = _parse_job(item, track)
                    if not record: continue
                    
                    job_id = record.metadata.job_id
                    if job_id in seen_ids or storage.has("meituan", track, job_id):
                        continue
                    
                    seen_ids.add(job_id)
                    storage.save("meituan", track, job_id, record.metadata.url, record.model_dump())
                    _append_jsonl(out_file, record)
                    yielded += 1
                    page_new += 1

                print(f"  [PAGE] {page_no:>3}  captured={len(job_list)}  new={page_new}  cumulative={yielded}")

                if limit > 0 and yielded >= limit:
                    print(f"\n[OK] Reached limit={limit}")
                    break

                # 翻页
                next_btn = page.locator(SELECTOR_NEXT)
                if not await next_btn.is_visible():
                    print("  [DONE] Next button invisible.")
                    break
                    
                classes = await next_btn.get_attribute("class") or ""
                if CLASS_DISABLED in classes:
                    print(f"  [DONE] Final page reached: {page_no}")
                    break
                
                await next_btn.scroll_into_view_if_needed()
                await next_btn.click()
                
                page_no += 1
                # 随机等待模拟人类行为
                await asyncio.sleep(random.uniform(2.0, 4.0))

        except Exception as e:
            print(f"\n[ERROR] {e}")
            raise
        finally:
            storage.close()
            await browser.close()

    return yielded
