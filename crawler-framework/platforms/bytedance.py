from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from playwright.async_api import Page

from ..base import CrawlContext, PlatformCrawler
from ..models import BasicInfo, JobRecord, Metadata, Requirements
from ..storage import ensure_parent_dir
from ..util import now_utc


class ByteDanceCrawler(PlatformCrawler):
    """
    字节跳动站点对搜索接口有 _signature 保护。
    为了稳定性，这里不自行计算签名，而是：
    - 让页面自己发起接口请求（签名由前端生成）
    - 监听并抓取 /api/v1/search/job/posts 的 JSON 响应
    - 从响应中抽取 job_post_list
    """

    platform = "bytedance"

    async def open_home(self, ctx: CrawlContext, page: Page) -> None:
        # 站点路径约定：experienced / campus / intern
        # 若未来路径变更，至少保证还能回退到社招页执行启发式抓取
        path = {"experienced": "experienced", "campus": "campus", "intern": "intern"}.get(ctx.track, "experienced")
        await page.goto(f"https://jobs.bytedance.com/{path}/position", wait_until="domcontentloaded")

    def _category_path(self, job_category: dict[str, Any] | None) -> list[str]:
        if not isinstance(job_category, dict):
            return []
        parent = job_category.get("parent")
        out: list[str] = []
        if isinstance(parent, dict) and parent.get("name"):
            out.append(str(parent["name"]))
        if job_category.get("name"):
            out.append(str(job_category["name"]))
        return out

    def _publish_date(self, publish_time_ms: int | None) -> str | None:
        if not publish_time_ms:
            return None
        dt = datetime.fromtimestamp(publish_time_ms / 1000, tz=timezone.utc)
        return dt.date().isoformat()

    async def crawl(self, ctx: CrawlContext, page: Page, state: dict[str, Any]) -> AsyncIterator[JobRecord]:
        captured: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

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

        out_dir = Path("data/raw/bytedance") / ctx.track
        ensure_parent_dir(out_dir / "x.json")

        # 断点续爬：持久化去重（跨多次运行）
        # 注意：state 的落盘由 main 在“收到 yield 后”立即触发，所以必须在 yield 之前更新 state。
        persisted_seen: set[str] = set()
        state_seen_list: list[str] = []
        try:
            raw_seen = state.get("seen_job_ids") or []
            if isinstance(raw_seen, list):
                state_seen_list = [str(x) for x in raw_seen if str(x).strip()]
                persisted_seen = set(state_seen_list)
        except Exception:
            persisted_seen = set()
            state_seen_list = []

        # 兼容老版本 state（只有 count，没有 seen_job_ids）：从已有输出文件回填去重集合
        if not state_seen_list:
            try:
                if ctx.output_jsonl.exists():
                    with ctx.output_jsonl.open("r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                                mid = obj.get("metadata") if isinstance(obj, dict) else None
                                jid = str((mid or {}).get("job_id") or "").strip()
                                if jid and jid not in persisted_seen:
                                    persisted_seen.add(jid)
                                    state_seen_list.append(jid)
                            except Exception:
                                continue
                    if state_seen_list:
                        state["seen_job_ids"] = state_seen_list
            except Exception:
                pass

        yielded_total = int(state.get("count", 0) or 0)
        seen_job_ids_this_run: set[str] = set()
        dumped = 0
        stable_rounds = 0
        last_yielded = 0

        # 持续滚动并消费新响应，直到达到 limit 或长时间没有新数据
        while True:
            # 尝试触发“下一页/加载更多”，优先点击按钮，其次滚动
            clicked = await page.evaluate(
                """
() => {
  const texts = ['下一页', '加载更多', '更多', 'Next'];
  const btns = Array.from(document.querySelectorAll('button,a')).filter(el => {
    const t = (el.innerText || '').trim();
    return t && texts.some(x => t.includes(x));
  });
  const visible = btns.find(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  });
  if (visible) { visible.click(); return true; }
  return false;
}
                """
            )
            if not clicked:
                try:
                    await page.keyboard.press("End")
                except Exception:
                    pass
                try:
                    await page.mouse.wheel(0, 5200)
                except Exception:
                    pass
            await page.wait_for_timeout(1400)

            # 把本轮新增的响应全部处理掉
            while dumped < len(captured):
                item = captured[dumped]
                (out_dir / f"job_posts_resp_{dumped:04d}.json").write_text(
                    json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                dumped += 1

                job_list = (((item.get("data") or {}).get("data") or {}).get("job_post_list") or [])
                if not isinstance(job_list, list):
                    continue
                for job in job_list:
                    if not isinstance(job, dict):
                        continue
                    job_id = str(job.get("id") or "").strip()
                    if not job_id:
                        continue
                    # 本次运行内去重 + 跨运行持久化去重
                    if job_id in seen_job_ids_this_run or job_id in persisted_seen:
                        continue
                    seen_job_ids_this_run.add(job_id)
                    persisted_seen.add(job_id)
                    state_seen_list.append(job_id)

                    title = str(job.get("title") or "").strip()
                    city_list = job.get("city_list") if isinstance(job.get("city_list"), list) else []
                    locations = [
                        str(c.get("name")).strip()
                        for c in city_list
                        if isinstance(c, dict) and isinstance(c.get("name"), str) and c.get("name").strip()
                    ]
                    desc = str(job.get("description") or "").strip()
                    req = str(job.get("requirement") or "").strip()
                    raw_jd_text = "\n".join([p for p in [desc, req] if p])

                    # 在 yield 前更新 state，保证 main 每条保存时 state 不会“落后一步”
                    yielded_total += 1
                    state["count"] = yielded_total
                    state["seen_job_ids"] = state_seen_list

                    yield JobRecord(
                        metadata=Metadata(platform=ctx.platform, track=ctx.track, crawl_timestamp=now_utc(), job_id=job_id),
                        basic_info=BasicInfo(
                            job_title=title or job_id,
                            category_path=self._category_path(job.get("job_category")),
                            location=locations,
                            publish_date=self._publish_date(job.get("publish_time")),
                        ),
                        requirements=Requirements(
                            education_level=None,
                            experience_years=None,
                            raw_jd_text=raw_jd_text,
                        ),
                    )
                    if ctx.limit is not None and len(seen_job_ids_this_run) >= ctx.limit:
                        return

            if len(seen_job_ids_this_run) == last_yielded:
                stable_rounds += 1
            else:
                stable_rounds = 0
                last_yielded = len(seen_job_ids_this_run)

            # 连续多轮没新增，认为加载停止
            if stable_rounds >= 8:
                return

