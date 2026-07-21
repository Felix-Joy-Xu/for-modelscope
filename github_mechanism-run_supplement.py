"""
补充采集主入口
============================================

使用方式:

  # 步骤0: 设置 GitHub Token（仅 M1/M2 需要）
  $env:GITHUB_TOKEN = "ghp_your_token_here"

  # 步骤1: 先跑 M4 话语编码（不需要 API，立即出结果）
  python run_supplement.py --m4-code

  # 步骤2: 采集 M1 PR 结构化数据（需要 API）
  python run_supplement.py --m1 --repo microsoft/vscode    # 先测一个仓库
  python run_supplement.py --m1                              # 所有核心仓库
  python run_supplement.py --m1 --fast                       # 快速模式（跳过review详情）

  # 步骤3: 采集 M2 贡献者流动性（需要 API）
  python run_supplement.py --m2 --repo microsoft/vscode
  python run_supplement.py --m2

  # 步骤4: 生成分析报告
  python run_supplement.py --report

  # 一次全跑（M4编码 + M1 + M2 + 报告）
  python run_supplement.py --all

  # 其他
  python run_supplement.py --check-rate                      # 检查 API 配额
  python run_supplement.py --status                          # 查看采集进度

API 消耗预估:
  M4 话语编码: 0 次 API 调用（读取本地已有数据）
  M1 全量采集(4核心仓库): ~15,000-25,000 次 API 调用（约 5-8 小时）
  M1 快速模式(4核心仓库): ~3,000-5,000 次 API 调用（约 1-2 小时）
  M2 全量采集(8仓库): ~1,200 次 API 调用（约 30 分钟）
"""

import argparse
import logging
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supplement_config import TARGET_REPOS, SUPPLEMENT_DB, OUTPUT_DIR
from supplement_db import SupplementDB
from github_api import GitHubClient
from collect_m1_prs import collect_prs_for_repo
from collect_m2_mobility import collect_mobility_for_repo
from code_existing_m4 import code_existing_threads
from supplement_report import generate_supplement_report


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    log_file = os.path.join(
        os.path.dirname(__file__),
        f"supplement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def parse_args():
    p = argparse.ArgumentParser(
        description="补充采集工具 — 对现有 github_threads.db 的缺口进行精准补采",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python run_supplement.py --m4-code                   # 先跑，不花 API
    python run_supplement.py --m1 --fast                  # M1 快速模式
    python run_supplement.py --m1 --repo microsoft/vscode # 指定仓库
    python run_supplement.py --m2                         # M2 贡献者流动性
    python run_supplement.py --report                     # 仅生成报告
    python run_supplement.py --all                        # 全部执行
    python run_supplement.py --status                     # 查看进度
        """
    )
    p.add_argument("--all", action="store_true", help="执行全部任务")
    p.add_argument("--m4-code", action="store_true",
                   help="对现有评论进行 M4 话语编码（不需要 API）")
    p.add_argument("--m1", action="store_true",
                   help="采集 M1 PR 结构化数据（需要 API）")
    p.add_argument("--m2", action="store_true",
                   help="采集 M2 贡献者流动性（需要 API）")
    p.add_argument("--report", action="store_true", help="生成分析报告")
    p.add_argument("--repo", type=str, help="指定单个仓库")
    p.add_argument("--fast", action="store_true",
                   help="快速模式（跳过 review 详情，减少 M2 贡献者数）")
    p.add_argument("--core-only", action="store_true",
                   help="仅处理核心仓库（thread > 200）")
    p.add_argument("--check-rate", action="store_true", help="检查 API 配额")
    p.add_argument("--status", action="store_true", help="查看采集进度")
    p.add_argument("--resume", action="store_true",
                   help="断点续传模式：跳过已采集的 PR/贡献者，从中断处继续")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def get_repos(args) -> dict:
    if args.repo:
        if args.repo in TARGET_REPOS:
            return {args.repo: TARGET_REPOS[args.repo]}
        return {args.repo: {"ai_adoption_date": "2023-06-01", "org_type": "未知", "priority": "手动"}}
    if args.core_only:
        return {k: v for k, v in TARGET_REPOS.items() if v.get("priority") == "核心"}
    return TARGET_REPOS


def show_status(db: SupplementDB):
    """显示采集进度。"""
    print("\n" + "=" * 60)
    print("采集进度")
    print("=" * 60)

    # M1
    rows = db.query("""
        SELECT repo_id, COUNT(*) as n, period
        FROM m1_pr_metrics
        GROUP BY repo_id, period
        ORDER BY repo_id
    """)
    print("\n[M1] PR 结构化数据:")
    if rows:
        for r in rows:
            print(f"  {r['repo_id']}: {r['n']} PRs ({r['period']})")
    else:
        print("  (暂无数据)")

    # M2
    rows = db.query("""
        SELECT home_repo, period, COUNT(*) as n
        FROM m2_mobility
        GROUP BY home_repo, period
        ORDER BY home_repo
    """)
    print("\n[M2] 贡献者流动性:")
    if rows:
        for r in rows:
            print(f"  {r['home_repo']}: {r['n']} 人 ({r['period']})")
    else:
        print("  (暂无数据)")

    # M4
    rows = db.query("""
        SELECT repo_id, COUNT(*) as n,
               SUM(individual_blame + ai_attribution + systemic_attribution +
                   accountability_gap + workflow_shift + skill_anxiety) as total_hits
        FROM m4_coded_comments
        GROUP BY repo_id
        ORDER BY n DESC
    """)
    print("\n[M4] 话语编码:")
    if rows:
        total = sum(r["n"] for r in rows)
        total_hits = sum(r["total_hits"] or 0 for r in rows)
        for r in rows:
            print(f"  {r['repo_id']}: {r['n']} 条, {r['total_hits'] or 0} 次命中")
        print(f"  总计: {total} 条, {total_hits} 次命中")
    else:
        print("  (暂无数据)")

    # 日志
    rows = db.query("""
        SELECT task, repo_id, action, count, message, timestamp
        FROM collection_log
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    print("\n最近日志:")
    for r in rows:
        print(f"  [{r['timestamp']}] {r['task']} {r['repo_id']}: {r['action']} ({r['count']})")

    print()


def main():
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger("main")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    db = SupplementDB(SUPPLEMENT_DB)

    # ---- 状态查看 ----
    if args.status:
        show_status(db)
        db.close()
        return

    # ---- API 配额 ----
    if args.check_rate:
        client = GitHubClient()
        data = client.check_rate_limit()
        if data:
            core = data.get("resources", {}).get("core", {})
            search = data.get("resources", {}).get("search", {})
            print(f"\nCore:   {core.get('remaining')}/{core.get('limit')}")
            print(f"Search: {search.get('remaining')}/{search.get('limit')}")
        db.close()
        return

    # 确定任务
    do_m4 = args.all or args.m4_code
    do_m1 = args.all or args.m1
    do_m2 = args.all or args.m2
    do_report = args.all or args.report

    if not any([do_m4, do_m1, do_m2, do_report]):
        print("请指定任务。用 --help 查看选项。")
        print("\n推荐顺序:")
        print("  1. python run_supplement.py --m4-code    # 不花 API，立即出结果")
        print("  2. python run_supplement.py --m1 --fast  # 快速采集 PR 数据")
        print("  3. python run_supplement.py --m2         # 贡献者流动性")
        print("  4. python run_supplement.py --report     # 生成报告")
        db.close()
        return

    repos = get_repos(args)
    start_time = datetime.now()

    logger.info("=" * 60)
    logger.info("补充采集任务")
    logger.info(f"  M4话语编码: {do_m4}")
    logger.info(f"  M1 PR数据: {do_m1}")
    logger.info(f"  M2 流动性: {do_m2}")
    logger.info(f"  目标仓库: {list(repos.keys())}")
    logger.info(f"  快速模式: {args.fast}")
    logger.info("=" * 60)

    # ---- M4: 话语编码（不需要 API） ----
    if do_m4:
        logger.info("\n" + "=" * 40)
        logger.info("任务: M4 话语编码（对现有数据）")
        logger.info("=" * 40)
        try:
            count = code_existing_threads(db)
            logger.info(f"M4 编码完成: {count} 条")
        except Exception as e:
            logger.error(f"M4 编码失败: {e}", exc_info=True)

    # ---- 需要 API 的任务 ----
    client = None
    if do_m1 or do_m2:
        client = GitHubClient()

    # ---- M1: PR 结构化数据 ----
    if do_m1:
        for repo_id, config in repos.items():
            logger.info(f"\n{'='*40}")
            logger.info(f"M1: {repo_id}")
            logger.info(f"{'='*40}")
            try:
                count = collect_prs_for_repo(
                    client, db, repo_id, config,
                    with_review_detail=not args.fast,
                    resume=args.resume,
                )
                logger.info(f"M1 {repo_id}: {count} PRs")
            except Exception as e:
                logger.error(f"M1 {repo_id} 失败: {e}", exc_info=True)

    # ---- M2: 贡献者流动性 ----
    if do_m2:
        for repo_id, config in repos.items():
            logger.info(f"\n{'='*40}")
            logger.info(f"M2: {repo_id}")
            logger.info(f"{'='*40}")
            try:
                max_c = 15 if args.fast else None
                count = collect_mobility_for_repo(
                    client, db, repo_id, config,
                    max_contributors=max_c,
                    use_search=not args.fast,
                    resume=args.resume,
                )
                logger.info(f"M2 {repo_id}: {count} contributors")
            except Exception as e:
                logger.error(f"M2 {repo_id} 失败: {e}", exc_info=True)

    # ---- 报告 ----
    if do_report or do_m4 or do_m1 or do_m2:
        logger.info("\n生成分析报告...")
        try:
            generate_supplement_report(db)
            logger.info(f"报告已保存到 {OUTPUT_DIR}/")
        except Exception as e:
            logger.error(f"报告生成失败: {e}", exc_info=True)

    elapsed = (datetime.now() - start_time).total_seconds()
    api_calls = client.request_count if client else 0
    logger.info(f"\n{'='*60}")
    logger.info(f"全部完成！耗时 {elapsed:.0f}s, API 调用 {api_calls} 次")
    logger.info(f"数据库: {SUPPLEMENT_DB}")
    logger.info(f"{'='*60}")

    db.close()


if __name__ == "__main__":
    main()
