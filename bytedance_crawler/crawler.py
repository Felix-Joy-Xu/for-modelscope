"""字节跳动招聘爬虫核心逻辑.

策略：使用 Playwright 打开招聘页面，拦截浏览器发出的 API 请求
（/api/v1/search/job/posts），直接从 JSON 响应中提取数据。
浏览器负责生成签名参数，我们只需读取响应。
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import Page, Response, async_playwright

from models import BasicInfo, JobRecord, Metadata, Requirements
from storage import Storage

# ──────────────────────── 配置 ────────────────────────

TRACK_URLS = {
    "experienced": "https://jobs.bytedance.com/experienced/position",
    "campus":      "https://jobs.bytedance.com/campus/position",
    "intern":      "https://jobs.bytedance.com/campus/position",   # 实习也从 campus 入口
}

API_PATTERN = "/api/v1/search/job/posts"
PAGE_SIZE = 1000          # 每次请求的 limit
MAX_EMPTY_PAGES = 3       # 连续空页后停止
MAX_RETRIES = 3           # 单次请求最大重试次数
DELAY_RANGE = (1.5, 3.5)  # 请求间随机延迟（秒）


# ──────────────────────── 数据解析 ────────────────────────

def _parse_publish_date(ts_ms: int | None) -> str | None:
    """将毫秒时间戳转为 YYYY-MM-DD."""
    if not ts_ms:
        return None
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.date().isoformat()


def _parse_category(cat: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """提取中/英文类别路径，如 (["研发","后端"], ["R&D","Backend"])."""
    if not isinstance(cat, dict):
        return [], []
    zh, en = [], []

    parent = cat.get("parent")
    if isinstance(parent, dict):
        name = (parent.get("name") or "").strip()
        en_name = (parent.get("en_name") or "").strip()
        if name:
            zh.append(name)
        if en_name:
            en.append(en_name)

    name = (cat.get("name") or "").strip()
    en_name = (cat.get("en_name") or "").strip()
    if name:
        zh.append(name)
    if en_name:
        en.append(en_name)

    return zh, en


def _parse_locations(job: dict[str, Any]) -> list[str]:
    """从 city_list 或 city_info 中提取城市列表."""
    locations: list[str] = []

    # 优先用 city_list（数组）
    city_list = job.get("city_list")
    if isinstance(city_list, list):
        for c in city_list:
            if isinstance(c, dict):
                name = (c.get("name") or "").strip()
                if name and name not in locations:
                    locations.append(name)

    # 备选：city_info（单个对象）
    if not locations:
        city_info = job.get("city_info")
        if isinstance(city_info, dict):
            name = (city_info.get("name") or "").strip()
            if name:
                locations.append(name)

    return locations


def _parse_job(job: dict[str, Any], track: str) -> JobRecord | None:
    """将 API 返回的单条岗位 JSON 解析为 JobRecord."""
    raw_id = job.get("id")
    if raw_id is None:
        return None
    job_id = str(raw_id).strip()
    if not job_id:
        return None

    title = (job.get("title") or "").strip() or job_id
    sub_title = (job.get("sub_title") or None)
    if isinstance(sub_title, str):
        sub_title = sub_title.strip() or None

    desc = (job.get("description") or "").strip()
    req = (job.get("requirement") or "").strip()
    raw_jd = "\n".join(x for x in [desc, req] if x).strip()

    cat_zh, cat_en = _parse_category(job.get("job_category"))
    locs = _parse_locations(job)
    pub_date = _parse_publish_date(job.get("publish_time"))

    url = (job.get("post_url") or job.get("job_url") or "").strip()
    if not url:
        # 构造详情页 URL
        track_slug = "campus" if track in ("campus", "intern") else "experienced"
        url = f"https://jobs.bytedance.com/{track_slug}/position/{job_id}/detail"

    return JobRecord(
        metadata=Metadata(
            platform="bytedance",
            track=track,
            crawl_timestamp=datetime.now(timezone.utc).isoformat(),
            job_id=job_id,
            url=url,
        ),
        basic_info=BasicInfo(
            job_title=title,
            sub_title=sub_title,
            category_path=cat_zh,
            category_en_path=cat_en,
            location=locs,
            publish_date=pub_date,
        ),
        requirements=Requirements(
            description=desc,
            requirement=req,
            raw_jd_text=raw_jd,
        ),
    )


# ──────────────────────── 输出 ────────────────────────

def _append_jsonl(path: Path, record: JobRecord) -> None:
    """追加写入一行 JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json(ensure_ascii=False))
        f.write("\n")


# ──────────────────────── 核心爬取 ────────────────────────

async def _wait_for_api_response(page: Page, timeout: int = 25_000) -> Response | None:
    """等待 API 响应（拦截浏览器自动发出的请求）."""
    try:
        async with page.expect_response(
            lambda r: API_PATTERN in (r.url or ""),
            timeout=timeout,
        ) as resp_info:
            pass
        return await resp_info.value
    except Exception:
        return None


async def crawl(
    track: str,
    output_dir: Path,
    db_path: Path,
    *,
    limit: int = 0,
    headed: bool = True,
) -> int:
    """
    爬取指定 track 的字节跳动岗位.

    参数:
        track:      "experienced" / "campus" / "intern"
        output_dir: JSONL 输出目录
        db_path:    SQLite 数据库路径
        limit:      抓取上限，0 表示全量
        headed:     是否显示浏览器窗口

    返回:
        本次新增记录数
    """
    base_url = TRACK_URLS.get(track)
    if not base_url:
        raise ValueError(f"不支持的 track: {track}")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"jobs_bytedance_{track}.jsonl"
    storage = Storage(db_path)

    print(f"\n{'='*60}")
    print(f"  [ByteDance Crawler] track={track}")
    print(f"  target: {'ALL' if limit == 0 else f'{limit}'}")
    print(f"  output: {out_file}")
    print(f"  db_existing: {storage.count('bytedance', track)}")
    print(f"{'='*60}\n")

    yielded = 0
    seen_ids: set[str] = set()
    empty_pages = 0
    offset = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        try:
            # 第一步：打开页面，建立会话和 cookie
            print("[1/3] Opening page...")
            await page.goto(base_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2500)

            # 如果是实习 track，尝试点击"实习"筛选
            if track == "intern":
                print("[1/3] Clicking intern filter...")
                try:
                    await page.evaluate("""
                        () => {
                            const keys = ['实习', 'ByteIntern', 'Intern'];
                            const nodes = Array.from(document.querySelectorAll('button,a,span,div'));
                            const cand = nodes.find(el => {
                                const t = (el.innerText || '').trim();
                                return t && keys.some(k => t.includes(k)) &&
                                       el.getBoundingClientRect().width > 0;
                            });
                            if (cand) { cand.click(); return true; }
                            return false;
                        }
                    """)
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass

            # 第二步：获取第一页数据
            print("[2/3] Start crawling (UI pagination)...\n")
            
            # 第一页的 API 会在 page.goto 或者稍微滞后一点时返回，我们通过重载页面来捕获第一页
            data: dict[str, Any] | None = None
            first_url = f"{base_url}?limit={PAGE_SIZE}"
            print(f"  [PAGE] initial load limit={PAGE_SIZE}")
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    async with page.expect_response(
                        lambda r: API_PATTERN in (r.url or "") and r.status == 200 and r.request.method == "POST",
                        timeout=25_000,
                    ) as resp_info:
                        await page.goto(first_url, wait_until="domcontentloaded", timeout=60_000)
                    resp = await resp_info.value
                    data = await resp.json()
                    break
                except Exception as e:
                    print(f"  [WARN] attempt {attempt} failed: {e}")
                    if attempt < MAX_RETRIES:
                        await page.wait_for_timeout(3000)
            
            page_index = 1
            while True:
                # 检查是否达到上限
                if limit > 0 and yielded >= limit:
                    print(f"\n[OK] Reached limit={limit}, stopping.")
                    break

                if data is None:
                    print(f"  [FAIL] Failed to get API response on page {page_index}.")
                    break

                # 提取 job_post_list
                job_list = ((data.get("data") or {}).get("job_post_list") or [])
                if not isinstance(job_list, list) or not job_list:
                    print(f"\n[DONE] No data on page {page_index}, ending.")
                    break

                page_new = 0
                for job in job_list:
                    if limit > 0 and yielded >= limit:
                        break
                    if not isinstance(job, dict):
                        continue

                    record = _parse_job(job, track)
                    if record is None:
                        continue

                    job_id = record.metadata.job_id
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    # 数据库去重
                    if storage.has("bytedance", track, job_id):
                        continue

                    # 保存
                    storage.save("bytedance", track, job_id, record.metadata.url, record.model_dump())
                    _append_jsonl(out_file, record)
                    yielded += 1
                    page_new += 1

                print(f"  [PAGE] {page_index:>3}  total={len(job_list)}  new={page_new}  cumulative={yielded}")

                # 获取下一页
                next_btn = page.locator("li.atsx-pagination-next:not(.atsx-pagination-disabled)").first
                if await next_btn.count() == 0:
                    break
                
                aria_disabled = await next_btn.get_attribute("aria-disabled")
                if aria_disabled == "true":
                    break
                
                # 随机延迟，模拟真实点击
                delay = random.uniform(*DELAY_RANGE)
                await page.wait_for_timeout(int(delay * 1000))

                page_index += 1
                data = None
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        async with page.expect_response(
                            lambda r: API_PATTERN in (r.url or "") and r.status == 200 and r.request.method == "POST",
                            timeout=25_000,
                        ) as resp_info:
                            # 确保元素可见且可点击
                            await next_btn.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            await next_btn.click()
                        resp = await resp_info.value
                        data = await resp.json()
                        break
                    except Exception as e:
                        print(f"  [WARN] Next Page attempt {attempt} failed: {e}")
                        if attempt < MAX_RETRIES:
                            await page.wait_for_timeout(3000)

            # 第三步：完成
            print(f"\n[3/3] Crawling complete!")
            print(f"  new_records: {yielded}")
            print(f"  db_total: {storage.count(track)}")
            print(f"  output: {out_file}")

        except Exception as e:
            # 错误时保存截图
            error_dir = output_dir.parent / "errors"
            error_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                await page.screenshot(path=str(error_dir / f"error_{track}_{ts}.png"), full_page=True)
            except Exception:
                pass
            print(f"\n[ERROR] {type(e).__name__}: {e}")
            raise
        finally:
            storage.close()
            await browser.close()

    return yielded
