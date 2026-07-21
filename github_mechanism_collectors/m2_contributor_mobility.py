"""
M2 采集器：贡献者跨仓库流动性追踪
对应论文 M2（技能权重重置与厂域锁定）

采集指标：
  - 在企业 AI 工具深度集成仓库活跃的 top 贡献者
  - 其外部开源社区贡献频率的前后变化
  - 跨仓库贡献者的流动性趋势

注意：GitHub Events API 只返回最近 90 天的数据，
历史数据需要通过 Search API 或其他方式获取。
"""

import json
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from typing import List, Dict

from github_api import GitHubClient
from database import MechanismDB
from config import M2_TOP_CONTRIBUTORS, M2_EXTERNAL_LOOKBACK_MONTHS
from collectors.m1_pr_lifecycle import is_bot_user

logger = logging.getLogger(__name__)


def collect_m2_contributors(
    client: GitHubClient, db: MechanismDB,
    owner: str, repo: str, repo_config: dict,
):
    """
    步骤一：获取目标仓库的 top 贡献者列表。
    """
    repo_id = f"{owner}/{repo}"
    logger.info(f"[M2] 采集 {repo_id} 的 top {M2_TOP_CONTRIBUTORS} 贡献者")

    db.log(repo_id, "M2", "start", message="采集贡献者列表")

    collected = 0
    for contributor in client.get_contributors(
        owner, repo, max_items=M2_TOP_CONTRIBUTORS
    ):
        username = contributor.get("login", "")
        contributions = contributor.get("contributions", 0)
        bot = is_bot_user(username)

        db.upsert_contributor(repo_id, username, contributions, bot)
        collected += 1

    db.log(repo_id, "M2", "contributors_done", items=collected,
           message=f"获取 {collected} 个贡献者")
    logger.info(f"[M2] {repo_id}: 获取 {collected} 个贡献者")

    return collected


def analyze_user_external_activity(
    client: GitHubClient, username: str, home_repo: str,
) -> Dict[str, dict]:
    """
    分析单个用户在 home_repo 之外的公开活动。

    注意：Events API 只返回最近 90 天数据。
    对于更长时间段的历史数据，需使用 Search API。

    返回: {
        "recent_90d": {
            "external_repos_count": int,
            "external_commits_count": int,
            "external_prs_count": int,
            "external_issues_count": int,
            "external_repos_list": [str],
        }
    }
    """
    home_owner_repo = home_repo.lower()

    external_repos = set()
    external_commits = 0
    external_prs = 0
    external_issues = 0

    try:
        events = list(client.get_user_events(username, max_items=300))
    except Exception as e:
        logger.warning(f"  获取 {username} 事件失败: {e}")
        return {}

    for event in events:
        event_repo = event.get("repo", {}).get("name", "").lower()
        event_type = event.get("type", "")

        # 排除 home repo
        if event_repo == home_owner_repo:
            continue

        external_repos.add(event_repo)

        if event_type == "PushEvent":
            commits_in_push = len(event.get("payload", {}).get("commits", []))
            external_commits += commits_in_push
        elif event_type == "PullRequestEvent":
            external_prs += 1
        elif event_type in ("IssuesEvent", "IssueCommentEvent"):
            external_issues += 1

    return {
        "recent_90d": {
            "external_repos_count": len(external_repos),
            "external_commits_count": external_commits,
            "external_prs_count": external_prs,
            "external_issues_count": external_issues,
            "external_repos_list": list(external_repos)[:50],  # 截断
        }
    }


def search_user_historical_activity(
    client: GitHubClient, username: str, home_repo: str,
    period_start: str, period_end: str,
) -> dict:
    """
    通过 Search API 获取用户在特定时间段的外部活动。

    使用 GitHub Search API 搜索用户在指定时间段的 PR 和 Issue。
    Search API 有更严格的限速（30 请求/分钟），需要谨慎使用。
    """
    home_owner = home_repo.split("/")[0] if "/" in home_repo else ""

    external_repos = set()
    external_prs = 0
    external_issues = 0

    # 搜索该用户在时间段内提交的 PR（排除 home repo）
    try:
        query = (
            f"author:{username} type:pr "
            f"created:{period_start}..{period_end} "
            f"-repo:{home_repo}"
        )
        for item in client.search_issues(query, max_items=100):
            repo_url = item.get("repository_url", "")
            # 提取 owner/repo
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                repo_name = f"{parts[-2]}/{parts[-1]}"
                external_repos.add(repo_name)
            external_prs += 1
    except Exception as e:
        logger.warning(f"  搜索 {username} PR 历史失败: {e}")

    # 搜索该用户在时间段内创建的 Issue
    try:
        query = (
            f"author:{username} type:issue "
            f"created:{period_start}..{period_end} "
            f"-repo:{home_repo}"
        )
        for item in client.search_issues(query, max_items=100):
            repo_url = item.get("repository_url", "")
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                repo_name = f"{parts[-2]}/{parts[-1]}"
                external_repos.add(repo_name)
            external_issues += 1
    except Exception as e:
        logger.warning(f"  搜索 {username} Issue 历史失败: {e}")

    return {
        "external_repos_count": len(external_repos),
        "external_commits_count": 0,  # Search API 无法直接获取 commit 数
        "external_prs_count": external_prs,
        "external_issues_count": external_issues,
        "external_repos_list": list(external_repos)[:50],
    }


def collect_m2_mobility(
    client: GitHubClient, db: MechanismDB,
    owner: str, repo: str, repo_config: dict,
    use_search_api: bool = True,
    max_contributors: int = None,
):
    """
    对目标仓库的 top 贡献者采集跨仓库流动性数据。

    Args:
        client: GitHub API 客户端
        db: 数据库实例
        owner, repo: 仓库标识
        repo_config: 仓库配置
        use_search_api: 是否使用 Search API 获取历史数据
                       （True 时可获取前后对比，但 API 消耗更大）
        max_contributors: 限制分析的贡献者数量
    """
    repo_id = f"{owner}/{repo}"
    ai_date = repo_config["ai_adoption_date"]
    adoption = datetime.fromisoformat(ai_date)

    top_n = max_contributors or M2_TOP_CONTRIBUTORS
    logger.info(f"[M2] 开始采集 {repo_id} top {top_n} 贡献者的跨仓库活动")

    db.log(repo_id, "M2", "mobility_start",
           message=f"分析 top {top_n} 贡献者")

    # 获取贡献者列表
    contributors = list(client.get_contributors(owner, repo, max_items=top_n))
    analyzed = 0

    for contrib in contributors:
        username = contrib.get("login", "")
        contributions = contrib.get("contributions", 0)

        if is_bot_user(username):
            continue

        logger.info(f"  分析 {username} ({contributions} commits)...")

        # 1. 最近 90 天活动（Events API）
        recent = analyze_user_external_activity(client, username, repo_id)
        if "recent_90d" in recent:
            data = recent["recent_90d"]
            record = {
                "username": username,
                "home_repo_id": repo_id,
                "home_contributions": contributions,
                "external_repos_count": data["external_repos_count"],
                "external_commits_count": data["external_commits_count"],
                "external_prs_count": data["external_prs_count"],
                "external_issues_count": data["external_issues_count"],
                "external_repos_list": json.dumps(
                    data["external_repos_list"], ensure_ascii=False
                ),
                "observation_period": "recent_90d",
                "period_start": (
                    datetime.now() - relativedelta(days=90)
                ).strftime("%Y-%m-%d"),
                "period_end": datetime.now().strftime("%Y-%m-%d"),
            }
            db.insert_contributor_mobility(record)

        # 2. 历史前后对比（Search API）
        if use_search_api:
            # Pre-AI 时期
            pre_start = (adoption - relativedelta(months=12)).strftime("%Y-%m-%d")
            pre_end = adoption.strftime("%Y-%m-%d")
            pre_data = search_user_historical_activity(
                client, username, repo_id, pre_start, pre_end
            )
            record_pre = {
                "username": username,
                "home_repo_id": repo_id,
                "home_contributions": contributions,
                "external_repos_count": pre_data["external_repos_count"],
                "external_commits_count": pre_data["external_commits_count"],
                "external_prs_count": pre_data["external_prs_count"],
                "external_issues_count": pre_data["external_issues_count"],
                "external_repos_list": json.dumps(
                    pre_data["external_repos_list"], ensure_ascii=False
                ),
                "observation_period": "pre_ai",
                "period_start": pre_start,
                "period_end": pre_end,
            }
            db.insert_contributor_mobility(record_pre)

            # Post-AI 时期
            post_start = adoption.strftime("%Y-%m-%d")
            post_end = min(
                adoption + relativedelta(months=12),
                datetime.now()
            ).strftime("%Y-%m-%d")
            post_data = search_user_historical_activity(
                client, username, repo_id, post_start, post_end
            )
            record_post = {
                "username": username,
                "home_repo_id": repo_id,
                "home_contributions": contributions,
                "external_repos_count": post_data["external_repos_count"],
                "external_commits_count": post_data["external_commits_count"],
                "external_prs_count": post_data["external_prs_count"],
                "external_issues_count": post_data["external_issues_count"],
                "external_repos_list": json.dumps(
                    post_data["external_repos_list"], ensure_ascii=False
                ),
                "observation_period": "post_ai",
                "period_start": post_start,
                "period_end": post_end,
            }
            db.insert_contributor_mobility(record_post)

        analyzed += 1
        if analyzed % 10 == 0:
            logger.info(f"  已分析 {analyzed}/{len(contributors)} 个贡献者")

    db.log(repo_id, "M2", "complete", items=analyzed,
           message=f"分析 {analyzed} 个贡献者的跨仓库活动")
    logger.info(f"[M2] {repo_id} 完成: 分析 {analyzed} 个贡献者")

    return analyzed
