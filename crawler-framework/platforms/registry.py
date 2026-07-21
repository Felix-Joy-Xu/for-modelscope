from __future__ import annotations

from typing import Dict

from ..base import PlatformCrawler
from ..models import Platform
from .alibaba import AlibabaCrawler
from .bytedance import ByteDanceCrawler
from .stub import StubCrawler


def get_crawlers() -> Dict[Platform, PlatformCrawler]:
    # 先提供可运行的占位实现；调研完各平台DOM后在此注册真实实现
    def mk(p: Platform) -> PlatformCrawler:
        if p == "bytedance":
            return ByteDanceCrawler()
        if p == "alibaba":
            return AlibabaCrawler()
        c = StubCrawler()
        c.platform = p
        return c

    return {p: mk(p) for p in ["bytedance", "tencent", "alibaba", "meituan"]}

