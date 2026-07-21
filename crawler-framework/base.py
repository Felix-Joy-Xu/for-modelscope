from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page

from .models import JobRecord, Platform, Track


class CrawlContext:
    def __init__(
        self,
        platform: Platform,
        track: Track,
        output_jsonl: Path,
        state_path: Path,
        limit: int | None,
        proxy: str | None = None,
        headless: bool = True,
    ) -> None:
        self.platform = platform
        self.track = track
        self.output_jsonl = output_jsonl
        self.state_path = state_path
        self.limit = limit
        self.proxy = proxy
        self.headless = headless


class PlatformCrawler(ABC):
    platform: Platform

    @abstractmethod
    async def open_home(self, ctx: CrawlContext, page: Page) -> None: ...

    @abstractmethod
    async def crawl(self, ctx: CrawlContext, page: Page, state: dict[str, Any]) -> AsyncIterator[JobRecord]: ...

    async def create_context(self, browser: Browser, user_agent: str, proxy: str | None) -> BrowserContext:
        return await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 720},
            proxy={"server": proxy} if proxy else None,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

