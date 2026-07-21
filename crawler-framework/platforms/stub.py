from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

from playwright.async_api import Page

from ..base import CrawlContext, PlatformCrawler
from ..heuristics import extract_job_like_dicts, normalize_from_job_dict
from ..models import BasicInfo, JobRecord, Metadata, Requirements
from ..storage import ensure_parent_dir
from ..util import now_utc


class StubCrawler(PlatformCrawler):
    platform = "bytedance"  # registry里会覆盖语义；占位不用于真实产出

    async def open_home(self, ctx: CrawlContext, page: Page) -> None:
        home_urls = {
            "bytedance": "https://jobs.bytedance.com/experienced/position",
            "tencent": "https://careers.tencent.com/home.html",
            "alibaba": "https://talent.alibaba.com/?lang=zh",
            "meituan": "https://zhaopin.meituan.com/web/position",
        }
        await page.goto(home_urls.get(self.platform, "about:blank"), wait_until="domcontentloaded")

        # 最佳努力：根据 track 尝试点击站点内的“校招/实习/社招”入口
        # 由于各站 DOM/文案可能变化，这里失败也不阻塞，仍然抓取当前页面能触发的 JSON。
        keywords = {
            "experienced": ["社招", "社会招聘", "experienced", "社會招聘"],
            "campus": ["校招", "校园招聘", "campus", "校園招聘"],
            "intern": ["实习", "實習", "intern"],
        }.get(ctx.track, [])
        if keywords:
            try:
                await page.evaluate(
                    """
({ keywords }) => {
  const nodes = Array.from(document.querySelectorAll('a,button,span,div'));
  const cand = nodes.find(el => {
    const t = (el.innerText || '').trim();
    if (!t) return false;
    return keywords.some(k => t.toLowerCase().includes(String(k).toLowerCase()));
  });
  if (cand) { cand.click(); return true; }
  return false;
}
                    """,
                    {"keywords": keywords},
                )
                await page.wait_for_timeout(1200)
            except Exception:
                pass

    async def crawl(self, ctx: CrawlContext, page: Page, state: dict[str, Any]) -> AsyncIterator[JobRecord]:
        raw_dir = Path("data/raw") / ctx.platform / ctx.track
        captured: list[dict[str, Any]] = []

        async def on_response(resp) -> None:
            try:
                ct = (resp.headers.get("content-type") or "").lower()
                if "application/json" not in ct:
                    return
                data = await resp.json()
                captured.append({"url": resp.url, "data": data})
            except Exception:
                return

        page.on("response", on_response)

        # 触发若干次滚动/等待，尽量让列表页把首屏与后续分页/懒加载请求打出来
        for _ in range(8):
            try:
                await page.mouse.wheel(0, 1800)
            except Exception:
                pass
            await page.wait_for_timeout(900)

        ensure_parent_dir(raw_dir / "x.json")
        # 落盘原始 JSON（便于后续精确适配）
        for i, item in enumerate(captured[:200]):
            (raw_dir / f"resp_{i:03d}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        # 启发式从已捕获响应中直接产出尽可能多的职位对象
        yielded = 0
        for item in captured:
            job_dicts = extract_job_like_dicts(item.get("data"))
            for jd in job_dicts:
                norm = normalize_from_job_dict(jd)
                record = JobRecord(
                    metadata=Metadata(platform=ctx.platform, track=ctx.track, crawl_timestamp=now_utc(), job_id=norm["job_id"]),
                    basic_info=BasicInfo(
                        job_title=norm["job_title"],
                        category_path=norm["category_path"],
                        location=norm["location"],
                        publish_date=norm["publish_date"],
                    ),
                    requirements=Requirements(
                        education_level=None,
                        experience_years=None,
                        raw_jd_text=norm["raw_jd_text"],
                    ),
                )
                yield record
                yielded += 1
                if ctx.limit is not None and yielded >= ctx.limit:
                    return
