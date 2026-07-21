from __future__ import annotations

import argparse
import asyncio

from .main import run_once


def _platform_order() -> list[str]:
    # 用户要求：按顺序爬取 字节 → 阿里 → 腾讯
    return ["bytedance", "alibaba", "tencent"]


def _track_order() -> list[str]:
    # 用户要求：校招、社招、实习三类
    # 内部枚举：campus=校招, experienced=社招, intern=实习
    return ["campus", "experienced", "intern"]


async def run_batch(args: argparse.Namespace) -> None:
    for platform in _platform_order():
        for track in _track_order():
            one = argparse.Namespace(**vars(args))
            one.platform = platform
            one.track = track
            print(f"==> crawl platform={platform} track={track}", flush=True)
            c = await run_once(one)
            print(f"<== done platform={platform} track={track} count={c}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default=r"C:\Users\22735\Desktop\文献")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--proxy", default=None)
    p.add_argument("--headed", action="store_true")
    p.add_argument("--delay-min", type=float, default=0.6)
    p.add_argument("--delay-max", type=float, default=1.8)
    # 允许覆盖：默认每个平台/track 自动生成 output/state
    p.add_argument("--output", default=None)
    p.add_argument("--state", default=None)
    return p


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run_batch(args))


if __name__ == "__main__":
    main()

