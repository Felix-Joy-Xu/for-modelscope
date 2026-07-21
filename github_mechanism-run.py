"""
GitHub 机制化数据采集 — 主入口
===============================

使用方式:
    # 1. 先设置 GitHub Token
    set GITHUB_TOKEN=ghp_your_token_here

    # 2. 运行完整采集（所有机制 + 所有仓库）
    python run.py --all

    # 3. 只运行特定机制
    python run.py --m1              # 仅 M1: PR 生命周期
    python run.py --m4              # 仅 M4: 问责话语
    python run.py --m2              # 仅 M2: 贡献者流动性
    python run.py --analyze         # 仅生成分析报告（不采集新数据）

    # 4. 指定仓库
    python run.py --m1 --repo microsoft/vscode

    # 5. 快速模式（减少 API 调用）
    python run.py --m1 --fast       # 跳过 review 详情采集

    # 6. 检查 API 配额
    python run.py --check-rate

对应论文:
    M1 → PR生命周期与审查负担（H1可证伪条件的行为印证）
    M2 → 贡献者跨仓库流动性（H2可证伪条件的行为印证）
    M3 → 过程可见性与自动化控制（M1采集时附带收集）
    M4 → 问责话语编码（M4问责鸿沟的话语痕迹）
"""

import argparse
import logging
import sys
import os
from datetime import datetime

# 将当前目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TARGET_REPOS, OUTPUT_DIR
from github_api import GitHubClient
from database import MechanismDB
from collectors.m1_pr_lifecycle import collect_m1_for_repo
from collectors.m2_contributor_mobility import collect_m2_contributors, collect_m2_mobility
from collectors.m4_accountability import collect_m4_for_repo
from analyze import generate_report


def setup_logging(verbose: bool = False):
    """配置日志。"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(
                    os.path.dirname(__file__),
                    f"collection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                ),
                encoding="utf-8",
            ),
        ],
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="GitHub 机制化数据采集工具（对应论文 M1–M4）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python run.py --all                        # 完整采集
    python run.py --m1 --m4                    # 采集 M1 和 M4
    python run.py --m1 --repo microsoft/vscode # 指定仓库
    python run.py --analyze                    # 仅生成报告
    python run.py --check-rate                 # 检查 API 配额
        """
    )

    # 采集选项
    parser.add_argument("--all", action="store_true",
                        help="运行所有机制的完整采集")
    parser.add_argument("--m1", action="store_true",
                        help="M1: 采集 PR 生命周期与审查负担")
    parser.add_argument("--m2", action="store_true",
                        help="M2: 采集贡献者跨仓库流动性")
    parser.add_argument("--m4", action="store_true",
                        help="M4: 采集问责话语编码")
    parser.add_argument("--analyze", action="store_true",
                        help="根据已有数据生成分析报告")

    # 范围控制
    parser.add_argument("--repo", type=str, default=None,
                        help="指定单个仓库（如 microsoft/vscode）")
    parser.add_argument("--fast", action="store_true",
                        help="快速模式：跳过 review 详情、减少 M2 贡献者数")

    # 其他
    parser.add_argument("--check-rate", action="store_true",
                        help="检查 GitHub API 配额状态")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细日志输出")

    return parser.parse_args()


def get_target_repos(args) -> dict:
    """根据参数确定目标仓库。"""
    if args.repo:
        if args.repo in TARGET_REPOS:
            return {args.repo: TARGET_REPOS[args.repo]}
        else:
            # 使用默认配置
            return {args.repo: {
                "ai_adoption_date": "2023-06-01",
                "org_type": "未分类",
            }}
    return TARGET_REPOS


def main():
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger("main")

    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 初始化客户端和数据库
    client = GitHubClient()
    db = MechanismDB()

    # 检查 API 配额
    if args.check_rate:
        rate_info = client.check_rate_limit()
        if rate_info:
            core = rate_info.get("resources", {}).get("core", {})
            search = rate_info.get("resources", {}).get("search", {})
            print(f"\n{'='*50}")
            print(f"GitHub API 配额状态")
            print(f"{'='*50}")
            print(f"Core API:   {core.get('remaining', '?')}/{core.get('limit', '?')} 剩余")
            print(f"Search API: {search.get('remaining', '?')}/{search.get('limit', '?')} 剩余")
            print(f"{'='*50}\n")
        return

    # 确定要运行的机制
    run_m1 = args.all or args.m1
    run_m2 = args.all or args.m2
    run_m4 = args.all or args.m4
    run_analyze = args.all or args.analyze

    if not any([run_m1, run_m2, run_m4, run_analyze]):
        print("请指定至少一个操作。使用 --help 查看选项。")
        return

    repos = get_target_repos(args)
    total_start = datetime.now()

    logger.info(f"{'='*60}")
    logger.info(f"GitHub 机制化数据采集")
    logger.info(f"目标仓库: {list(repos.keys())}")
    logger.info(f"采集机制: M1={run_m1} M2={run_m2} M4={run_m4}")
    logger.info(f"快速模式: {args.fast}")
    logger.info(f"{'='*60}")

    # ---- 采集仓库基本信息 ----
    for repo_full, config in repos.items():
        owner, repo = repo_full.split("/")
        logger.info(f"\n{'='*40}")
        logger.info(f"仓库: {repo_full}")
        logger.info(f"{'='*40}")

        # 获取仓库信息
        repo_info = client.get_repo_info(owner, repo)
        if repo_info:
            repo_info["org_type"] = config.get("org_type", "")
            repo_info["ai_adoption_date"] = config.get("ai_adoption_date", "")
            db.upsert_repo(repo_full, repo_info)
            logger.info(
                f"  ★ {repo_info.get('stargazers_count', 0)} stars, "
                f"{repo_info.get('forks_count', 0)} forks, "
                f"语言: {repo_info.get('language', '?')}"
            )
        else:
            logger.warning(f"  无法获取仓库信息: {repo_full}")
            continue

        # ---- M1: PR 生命周期 ----
        if run_m1:
            try:
                count = collect_m1_for_repo(
                    client, db, owner, repo, config,
                    collect_review_detail=not args.fast,
                )
                logger.info(f"  [M1] 完成: {count} 个 PR")
            except Exception as e:
                logger.error(f"  [M1] 采集失败: {e}", exc_info=True)

        # ---- M4: 问责话语 ----
        if run_m4:
            try:
                count = collect_m4_for_repo(
                    client, db, owner, repo, config,
                    bug_only=False,
                )
                logger.info(f"  [M4] 完成: {count} 个 Issue")
            except Exception as e:
                logger.error(f"  [M4] 采集失败: {e}", exc_info=True)

        # ---- M2: 贡献者流动性 ----
        if run_m2:
            try:
                max_c = 20 if args.fast else None
                collect_m2_contributors(client, db, owner, repo, config)
                count = collect_m2_mobility(
                    client, db, owner, repo, config,
                    use_search_api=not args.fast,
                    max_contributors=max_c,
                )
                logger.info(f"  [M2] 完成: {count} 个贡献者")
            except Exception as e:
                logger.error(f"  [M2] 采集失败: {e}", exc_info=True)

    # ---- 生成分析报告 ----
    if run_analyze or run_m1 or run_m4 or run_m2:
        logger.info("\n" + "="*40)
        logger.info("生成分析报告...")
        try:
            report = generate_report(db)
            report_path = os.path.join(OUTPUT_DIR, "mechanism_analysis_report.md")
            logger.info(f"报告已保存: {report_path}")
        except Exception as e:
            logger.error(f"报告生成失败: {e}", exc_info=True)

    # 完成
    elapsed = (datetime.now() - total_start).total_seconds()
    logger.info(f"\n{'='*60}")
    logger.info(f"全部完成！耗时 {elapsed:.0f} 秒，共发送 {client.request_count} 次 API 请求")
    logger.info(f"数据库: {db.db_path}")
    logger.info(f"{'='*60}")

    db.close()


if __name__ == "__main__":
    main()
