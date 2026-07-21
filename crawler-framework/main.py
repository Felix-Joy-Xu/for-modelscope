from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright
from tenacity import RetryError, retry, stop_after_attempt, wait_random

from .base import CrawlContext
from .platforms.registry import get_crawlers
from .storage import append_jsonl, ensure_parent_dir, load_state, save_state
from .util import pick_user_agent, sleep_biomimetic


@retry(stop=stop_after_attempt(3), wait=wait_random(1, 3))
async def _goto(page, url: str) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)


def _default_out_dir() -> Path:
    # 用户指定：爬取结果存到桌面“文献”文件夹
    return Path(r"C:\Users\22735\Desktop\文献")


def _resolve_output(args: argparse.Namespace) -> Path:
    if args.output:
        return Path(args.output).resolve()
    out_dir = Path(args.out_dir).resolve()
    return (out_dir / f"jobs_{args.platform}_{args.track}.jsonl").resolve()


def _resolve_state(args: argparse.Namespace) -> Path:
    if args.state:
        return Path(args.state).resolve()
    out_dir = Path(args.out_dir).resolve()
    return (out_dir / "state" / f"state_{args.platform}_{args.track}.json").resolve()


async def run_once(args: argparse.Namespace) -> int:
    crawlers = get_crawlers()
    crawler = crawlers[args.platform]

    out = _resolve_output(args)
    state_path = _resolve_state(args)
    ensure_parent_dir(out)
    try:
        out.touch(exist_ok=True)
    except Exception:
        pass

    ctx = CrawlContext(
        platform=args.platform,
        track=args.track,
        output_jsonl=out,
        state_path=state_path,
        limit=args.limit,
        proxy=args.proxy,
        headless=not args.headed,
    )

    state: dict[str, Any] = load_state(state_path)
    added = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=ctx.headless)

        user_agent = pick_user_agent()
        context = await crawler.create_context(browser, user_agent=user_agent, proxy=ctx.proxy)
        page = await context.new_page()

        # 反检测（可选依赖）：playwright-stealth
        try:
            from playwright_stealth import stealth_async

            await stealth_async(page)
        except Exception:
            pass

        try:
            await crawler.open_home(ctx, page)
        except RetryError:
            await browser.close()
            raise

        try:
            async for record in crawler.crawl(ctx, page, state):
                append_jsonl(out, record)
                added += 1
                # 统一语义：state["count"] 表示累计已入库条数（跨多次运行）。
                # 各平台 crawler 也可能自行维护该字段，这里以“递增”方式保证不回退。
                state["count"] = int(state.get("count", 0) or 0) + 1
                save_state(state_path, state)
                sleep_biomimetic(args.delay_min, args.delay_max)
                if ctx.limit is not None and added >= ctx.limit:
                    break
        finally:
            # 兜底落盘：crawler 可能在退出前才补充 state（例如 seen_job_ids）
            try:
                save_state(state_path, state)
            except Exception:
                pass
            await context.close()
            await browser.close()

    return added


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--platform", choices=["bytedance", "tencent", "alibaba", "meituan"], required=True)
    p.add_argument(
        "--track",
        choices=["experienced", "campus", "intern"],
        default="experienced",
        help="岗位类别：experienced=社招, campus=校招, intern=实习",
    )
    p.add_argument("--out-dir", default=str(_default_out_dir()), help="输出目录（默认：桌面\\文献）")
    p.add_argument("--output", default=None, help="输出 jsonl 文件路径（不填则按 out-dir 自动生成）")
    p.add_argument("--state", default=None, help="断点续传 state.json 路径（不填则按 out-dir 自动生成）")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--proxy", default=None, help="形如 http://user:pass@ip:port 或 socks5://ip:port")
    p.add_argument("--headed", action="store_true", help="以有界面模式运行，便于调试")
    p.add_argument("--delay-min", type=float, default=0.6)
    p.add_argument("--delay-max", type=float, default=1.8)
    return p


def main() -> None:
    args = build_parser().parse_args()
    count = __import__("asyncio").run(run_once(args))
    print(f"done: {count}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()

