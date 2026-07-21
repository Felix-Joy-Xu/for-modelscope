from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from playwright.async_api import async_playwright


# =========================
# Models (PRD schema)
# =========================

Platform = Literal["bytedance", "tencent", "alibaba", "meituan"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sleep_biomimetic(min_s: float = 0.6, max_s: float = 1.8) -> None:
    lo = max(0.0, float(min_s))
    hi = max(lo, float(max_s))
    time.sleep(random.uniform(lo, hi))


def pick_user_agent() -> str:
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    return random.choice(uas)


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))
        f.write("\n")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def make_record(
    *,
    platform: Platform,
    job_id: str,
    job_title: str,
    category_path: list[str],
    location: list[str],
    publish_date: str | None,
    raw_jd_text: str,
) -> dict[str, Any]:
    return {
        "metadata": {
            "platform": platform,
            "crawl_timestamp": now_utc().isoformat().replace("+00:00", "Z"),
            "job_id": job_id,
        },
        "basic_info": {
            "job_title": job_title,
            "category_path": category_path,
            "location": location,
            "publish_date": publish_date,
        },
        "requirements": {
            "education_level": None,
            "experience_years": None,
            "raw_jd_text": raw_jd_text,
        },
    }


# =========================
# ByteDance (page-driven capture)
# =========================


async def crawl_bytedance(
    *,
    output_jsonl: Path,
    raw_dir: Path,
    state_path: Path,
    limit: int | None,
    headless: bool,
    proxy: str | None,
    delay_min: float,
    delay_max: float,
) -> int:
    """
    说明：
    - 字节 jobs API 受 _signature 保护
    - 本实现不尝试计算 _signature，而是监听页面自身发起的
      /api/v1/search/job/posts JSON 响应并抽取 job_post_list
    - 该方式通常可稳定抓到“首屏/首批”的职位数据；若需要全量，
      需要进一步实现站内分页点击与分类遍历（依赖页面结构变化）。
    """

    state = load_state(state_path)
    count = int(state.get("count") or 0)
    seen_job_ids: set[str] = set(state.get("seen_job_ids") or [])
    seen_urls: set[str] = set()
    captured: list[dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=pick_user_agent(),
            viewport={"width": 1280, "height": 720},
            proxy={"server": proxy} if proxy else None,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()

        # 可选 stealth
        try:
            from playwright_stealth import stealth_async

            await stealth_async(page)
        except Exception:
            pass

        async def on_response(resp) -> None:
            try:
                if "/api/v1/search/job/posts" not in resp.url:
                    return
                ct = (resp.headers.get("content-type") or "").lower()
                if "application/json" not in ct:
                    return
                if resp.url in seen_urls:
                    return
                seen_urls.add(resp.url)
                data = await resp.json()
                captured.append({"url": resp.url, "data": data})
            except Exception:
                return

        page.on("response", on_response)

        await page.goto("https://jobs.bytedance.com/experienced/position", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)

        # 深度分类遍历抓取 (用于突破 10,000 条限制)
        all_categories = ["研发", "运营", "产品", "职能 / 支持", "销售", "设计", "市场", "游戏策划", "教研教学"]
        
        for cat_name in all_categories:
            print(f"\n========== 开始抓取职类: {cat_name} ==========")
            
            try:
                # 重新加载页面，清理之前的状态
                await page.goto("https://jobs.bytedance.com/experienced/position", wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                
                # 字节的过滤区可能在侧边栏，尝试寻找分类文本
                # 使用通配定位器，寻找包含分类名称的元素并尝试点击
                cat_btn = page.get_by_text(cat_name, exact=True).first
                if await cat_btn.is_visible():
                    await cat_btn.click()
                    print(f"驱动成功：已选中职类 [{cat_name}]")
                    await page.wait_for_timeout(2000)
                else:
                    # 如果直接匹配失败，尝试点击展开可能存在的“职类”下拉框
                    filter_header = page.get_by_placeholder("职类").first
                    if await filter_header.is_visible():
                        await filter_header.click()
                        await page.wait_for_timeout(1000)
                        cat_btn = page.get_by_text(cat_name, exact=True).last
                        await cat_btn.click()
                        print(f"通过下拉框选中职类 [{cat_name}]")
                        await page.wait_for_timeout(2000)
                    else:
                        print(f"警告：未能在页面上定位到 [{cat_name}]")
                        continue
            except Exception as e:
                print(f"分类选择异常 ({cat_name}): {e}")
                continue

            # 2. 该分类下的翻页逻辑
            current_page = 1
            max_pages = 1000 # 单个分类通常不会超过 1000 页
            
            while current_page <= max_pages:
                print(f"--- [{cat_name}] 第 {current_page} 页 --- 累计去重总数: {count}")
                
                pre_click_count = len(captured)
                try:
                    next_btn = page.locator("li.atsx-pagination-next:not(.atsx-pagination-disabled)").first
                    if not await next_btn.is_visible():
                        await page.keyboard.press("End")
                        await page.wait_for_timeout(1000)
                    
                    if await next_btn.is_visible():
                        await next_btn.click()
                        current_page += 1
                        
                        # 等待新数据到达
                        timeout_start = time.time()
                        while len(captured) == pre_click_count and time.time() - timeout_start < 8:
                            await page.wait_for_timeout(500)
                    else:
                        print(f"分类 {cat_name} 抓取完毕。")
                        break
                except Exception as e:
                    print(f"翻页异常: {e}")
                    break
                
                # 实时处理并保存
                if len(captured) > pre_click_count:
                    new_responses = captured[pre_click_count:]
                    for resp in new_responses:
                        job_list = (((resp.get("data") or {}).get("data") or {}).get("job_post_list") or [])
                        for job in job_list:
                            if not isinstance(job, dict): continue
                            job_id = str(job.get("id") or "").strip()
                            if not job_id or job_id in seen_job_ids: continue
                            seen_job_ids.add(job_id)
                            
                            title = str(job.get("title") or "").strip()
                            locations = [str(c.get("name")) for c in (job.get("city_list") or []) if isinstance(c, dict)]
                            raw_jd = "\n".join([str(job.get("description") or ""), str(job.get("requirement") or "")])
                            
                            append_jsonl(output_jsonl, make_record(
                                platform="bytedance", job_id=job_id, job_title=title,
                                category_path=[cat_name], location=locations,
                                publish_date=None, raw_jd_text=raw_jd
                            ))
                            count += 1
                    
                    state["count"] = count
                    state["seen_job_ids"] = list(seen_job_ids)
                    save_state(state_path, state)

                if limit is not None and count >= limit:
                    break
                
                await page.wait_for_timeout(random.uniform(1500, 3000))

            if limit is not None and count >= limit:
                break

        print(f"全量抓取完成！最终捕获总数: {count}")
        await context.close()
        await browser.close()

    return count


# =========================
# CLI
# =========================


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--platform", choices=["bytedance"], default="bytedance")
    p.add_argument("--output", default=str(Path("data/out/jobs.jsonl")))
    p.add_argument("--state", default=str(Path("data/state/state.json")))
    p.add_argument("--raw-dir", default=str(Path("data/raw/bytedance")))
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--proxy", default=None)
    p.add_argument("--headed", action="store_true")
    p.add_argument("--delay-min", type=float, default=0.6)
    p.add_argument("--delay-max", type=float, default=1.8)
    return p


def main() -> None:
    args = build_parser().parse_args()
    output = Path(args.output).resolve()
    state = Path(args.state).resolve()
    raw_dir = Path(args.raw_dir).resolve()

    count = __import__("asyncio").run(
        crawl_bytedance(
            output_jsonl=output,
            raw_dir=raw_dir,
            state_path=state,
            limit=args.limit,
            headless=not args.headed,
            proxy=args.proxy,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
        )
    )
    print(f"done: {count}")


if __name__ == "__main__":
    main()

