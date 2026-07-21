"""运行入口 — 命令行启动爬虫."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(
        description="招聘网站统一爬虫入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--platform",
        choices=["bytedance", "alibaba", "tencent", "meituan"],
        default="bytedance",
        help="目标平台 (bytedance / alibaba / tencent / meituan)",
    )
    parser.add_argument(
        "--track",
        choices=["experienced", "campus", "intern", "all"],
        default="experienced",
        help="招聘轨道：experienced(社招) / campus(校招) / intern(实习) / all(全部)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="抓取上限，0 表示全量（默认 50 条试跑）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式（不显示浏览器窗口）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出目录（默认为项目根目录下的 outputs/）",
    )

    args = parser.parse_args()

    platform_name = args.platform
    if platform_name == "alibaba":
        from alibaba_crawler import crawl
    elif platform_name == "tencent":
        from tencent_crawler import crawl
    elif platform_name == "meituan":
        from meituan_crawler import crawl
    else:
        from crawler import crawl

    # 路径
    project_root = Path(__file__).parent
    output_dir = Path(args.output) if args.output else project_root / "outputs"
    db_path = project_root / "data" / f"{platform_name}.db"

    # 确定要跑的 track 列表
    if args.track == "all":
        tracks = ["experienced", "campus", "intern"]
    else:
        tracks = [args.track]

    headed = not args.headless
    total = 0

    for track in tracks:
        n = asyncio.run(
            crawl(
                track=track,
                output_dir=output_dir,
                db_path=db_path,
                limit=args.limit,
                headed=headed,
            )
        )
        total += n

    print(f"\n{'='*60}")
    print(f"  [{platform_name.upper()}] 全部完成！共抓取 {total} 条新记录")
    print(f"{'='*60}")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    main()
