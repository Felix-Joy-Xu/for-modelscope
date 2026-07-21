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


class AlibabaCrawler(PlatformCrawler):
    """
    阿里招聘站点 DOM 与接口可能变动较快，这里采用“稳健优先”的抓取策略：
    - 进入主页后，按 track（社招/校招/实习）最佳努力点击入口/标签
    - 监听页面产生的 JSON 响应并落盘，便于后续精确适配
    - 使用 heuristics 从未知 JSON 结构中启发式抽取职位对象并结构化输出
    """

    platform = "alibaba"

    async def open_home(self, ctx: CrawlContext, page: Page) -> None:
        # 经验：阿里校招/实习与社招可能分属不同入口页。这里按 track 优先直达“职位列表页”，
        # 若直达失败，再回退到首页做“点击入口”的最佳努力。
        candidates: list[str] = []
        if ctx.track == "campus":
            candidates = [
                "https://campus-talent.alibaba.com/?lang=zh",
                "https://talent.alibaba.com/campus/position-list?campusType=freshman&lang=zh",
                "https://talent.alibaba.com/campus/position-list?lang=zh",
            ]
        elif ctx.track == "intern":
            candidates = [
                "https://campus-talent.alibaba.com/?lang=zh",
                "https://talent.alibaba.com/campus/position-list?campusType=intern&lang=zh",
                "https://talent.alibaba.com/campus/position-list?campusType=internship&lang=zh",
                "https://talent.alibaba.com/campus/position-list?lang=zh",
            ]
        else:
            # experienced
            candidates = [
                "https://talent.alibaba.com/?lang=zh",
                "https://talent.alibaba.com/position-list?lang=zh",
                "https://talent.alibaba.com/off-campus/position-list?lang=zh",
            ]

        for url in candidates:
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(800)
                break
            except Exception:
                continue

        keywords = {
            "experienced": ["社招", "社会招聘", "社會招聘", "experienced", "社会"],
            "campus": ["校招", "校园招聘", "校園招聘", "campus", "应届", "應屆", "校園"],
            "intern": ["实习", "實習", "intern", "实習生"],
        }.get(ctx.track, [])

        # 最佳努力点击入口/Tab；失败不阻塞
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
        ensure_parent_dir(raw_dir / "x.json")
        url_log = raw_dir / "response_urls.txt"

        captured: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        async def on_response(resp) -> None:
            try:
                url = resp.url or ""
                # 记录所有响应 URL，便于后续精确适配接口
                try:
                    url_log.write_text((url_log.read_text(encoding="utf-8") if url_log.exists() else "") + url + "\n", encoding="utf-8")
                except Exception:
                    pass
                # 只保留更可能与“职位列表/搜索”相关的响应，避免配置类噪声淹没有效数据
                key_hits = ["position", "job", "recruit", "search", "list", "posts"]
                if not any(k in url.lower() for k in key_hits):
                    return
                if resp.url in seen_urls:
                    return
                seen_urls.add(resp.url)
                ct = (resp.headers.get("content-type") or "").lower()
                if "application/json" in ct:
                    data = await resp.json()
                    captured.append({"url": resp.url, "data": data})
                    return
                # 某些接口可能返回 text/plain 但仍是 JSON 字符串
                txt = await resp.text()
                try:
                    data = json.loads(txt)
                except Exception:
                    return
                captured.append({"url": resp.url, "data": data})
            except Exception:
                return

        page.on("response", on_response)

        # 多轮滚动/等待触发更多请求
        for _ in range(14):
            try:
                await page.mouse.wheel(0, 2200)
            except Exception:
                pass
            await page.wait_for_timeout(950)

        # 记录 HTML（用于定位接口/下一步精确适配）
        try:
            (raw_dir / "page.html").write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass

        # 落盘原始 JSON，便于之后写“精确接口解析”
        for i, item in enumerate(captured[:250]):
            (raw_dir / f"resp_{i:03d}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        yielded = 0
        seen_job_ids: set[str] = set()
        for item in captured:
            job_dicts = extract_job_like_dicts(item.get("data"))
            for jd in job_dicts:
                norm = normalize_from_job_dict(jd)
                job_id = (norm.get("job_id") or "").strip()
                if not job_id or job_id in seen_job_ids:
                    continue
                seen_job_ids.add(job_id)

                record = JobRecord(
                    metadata=Metadata(platform=ctx.platform, track=ctx.track, crawl_timestamp=now_utc(), job_id=job_id),
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

