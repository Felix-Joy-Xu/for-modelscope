"""
M2 补充采集：贡献者跨仓库流动性
============================================
追踪目标仓库 top 贡献者在外部开源社区的活动变化，
作为"厂域锁定"（技能权重重置）的行为代理变量。

对应论文:
  M2（技能权重重置与厂域锁定）行为印证：
    "在企业AI工具深度集成仓库活跃的贡献者，
     其在外部开源社区的贡献频率与质量是否同期下降"

API 消耗估算:
  每个贡献者: ~5 次请求（Events API 3页 + Search API 2次）
  每仓库 top 30: ~150 次请求
  8 仓库: ~1200 次请求
"""

import json
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict

from github_api import GitHubClient
from supplement_db import SupplementDB
from supplement_config import (
    TARGET_REPOS, BOT_PATTERNS,
    M2_TOP_CONTRIBUTORS, M2_USE_SEARCH_API,
)

logger = logging.getLogger(__name__)


def is_bot(username: str) -> bool:
    if not username:
        return False
    name = username.lower()
    if name.endswith("[bot]") or name.endswith("-bot"):
        return True
    return any(p in name for p in BOT_PATTERNS)


def analyze_recent_events(client: GitHubClient, username: str,
                          home_repo: str) -> dict:
    """通过 Events API 分析最近 90 天的外部活动。"""
    home = home_repo.lower()
    repos = set()
    commits = 0
    prs = 0
    issues = 0

    try:
        events = list(client.get_paginated(
            f"/users/{username}/events/public", max_items=300
        ))
    except Exception as e:
        logger.warning(f"  {username} 事件获取失败: {e}")
        return {"external_repos": 0, "external_commits": 0,
                "external_prs": 0, "external_issues": 0,
                "external_repos_list": []}

    for ev in events:
        ev_repo = ev.get("repo", {}).get("name", "").lower()
        if ev_repo == home:
            continue
        repos.add(ev_repo)
        typ = ev.get("type", "")
        if typ == "PushEvent":
            commits += len(ev.get("payload", {}).get("commits", []))
        elif typ == "PullRequestEvent":
            prs += 1
        elif typ in ("IssuesEvent", "IssueCommentEvent"):
            issues += 1

    return {
        "external_repos": len(repos),
        "external_commits": commits,
        "external_prs": prs,
        "external_issues": issues,
        "external_repos_list": list(repos)[:50],
    }


def search_historical(client: GitHubClient, username: str,
                      home_repo: str, start: str, end: str) -> dict:
    """通过 Search API 获取特定时间段的外部 PR/Issue 活动。"""
    repos = set()
    prs = 0
    issues = 0

    # 搜索 PR
    try:
        query = f"author:{username} type:pr created:{start}..{end} -repo:{home_repo}"
        for item in client.get_paginated("/search/issues",
                                          {"q": query, "sort": "created"},
                                          max_items=100):
            repo_url = item.get("repository_url", "")
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                repos.add(f"{parts[-2]}/{parts[-1]}")
            prs += 1
    except Exception as e:
        logger.warning(f"  {username} PR 搜索失败: {e}")

    # 搜索 Issue
    try:
        query = f"author:{username} type:issue created:{start}..{end} -repo:{home_repo}"
        for item in client.get_paginated("/search/issues",
                                          {"q": query, "sort": "created"},
                                          max_items=100):
            repo_url = item.get("repository_url", "")
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                repos.add(f"{parts[-2]}/{parts[-1]}")
            issues += 1
    except Exception as e:
        logger.warning(f"  {username} Issue 搜索失败: {e}")

    return {
        "external_repos": len(repos),
        "external_commits": 0,
        "external_prs": prs,
        "external_issues": issues,
        "external_repos_list": list(repos)[:50],
    }


def collect_mobility_for_repo(
    client: GitHubClient, db: SupplementDB,
    repo_id: str, config: dict,
    max_contributors: int = None,
    use_search: bool = True,
    resume: bool = False,
):
    """
    对单个仓库的 top 贡献者采集跨仓库流动性。

    支持断点续传：如果 resume=True，会跳过已采集完成的贡献者。
    """
    owner, repo = repo_id.split("/")
    ai_date = config["ai_adoption_date"]
    adoption = datetime.fromisoformat(ai_date)
    top_n = max_contributors or M2_TOP_CONTRIBUTORS

    logger.info(f"[M2] {repo_id}: 开始采集 top {top_n} 贡献者流动性")
    db.log("m2_mobility", repo_id, "start", message=f"top {top_n}")

    # ---- 断点续传：获取已完成的贡献者列表 ----
    completed = set()
    if resume:
        completed = db.get_completed_contributors(repo_id)
        if completed:
            logger.info(f"  断点续传模式：已有 {len(completed)} 个贡献者完成，将跳过")
        else:
            logger.info(f"  断点续传模式：无已有数据，从头开始")

    # 获取贡献者列表
    contributors = list(client.get_paginated(
        f"/repos/{owner}/{repo}/contributors", max_items=top_n
    ))

    analyzed = 0
    skipped = 0
    for contrib in contributors:
        username = contrib.get("login", "")
        contribs = contrib.get("contributions", 0)

        if is_bot(username):
            continue

        # ---- 断点续传：跳过已完成的贡献者 ----
        if resume and username in completed:
            skipped += 1
            continue

        db.upsert_contributor(repo_id, username, contribs, False)

        logger.info(f"  {username} ({contribs} commits)...")

        # 1. 最近 90 天（Events API）
        recent = analyze_recent_events(client, username, repo_id)
        db.upsert_mobility({
            "username": username,
            "home_repo": repo_id,
            "home_contributions": contribs,
            "external_repos": recent["external_repos"],
            "external_commits": recent["external_commits"],
            "external_prs": recent["external_prs"],
            "external_issues": recent["external_issues"],
            "external_repos_list": json.dumps(
                recent["external_repos_list"], ensure_ascii=False),
            "period": "recent_90d",
            "period_start": (datetime.now() - relativedelta(days=90)).strftime("%Y-%m-%d"),
            "period_end": datetime.now().strftime("%Y-%m-%d"),
        })

        # 2. 前后对比（Search API）
        if use_search:
            pre_start = (adoption - relativedelta(months=12)).strftime("%Y-%m-%d")
            pre_end = adoption.strftime("%Y-%m-%d")
            pre = search_historical(client, username, repo_id, pre_start, pre_end)
            db.upsert_mobility({
                "username": username,
                "home_repo": repo_id,
                "home_contributions": contribs,
                "external_repos": pre["external_repos"],
                "external_commits": pre["external_commits"],
                "external_prs": pre["external_prs"],
                "external_issues": pre["external_issues"],
                "external_repos_list": json.dumps(
                    pre["external_repos_list"], ensure_ascii=False),
                "period": "pre_ai",
                "period_start": pre_start,
                "period_end": pre_end,
            })

            post_start = adoption.strftime("%Y-%m-%d")
            post_end = min(adoption + relativedelta(months=12),
                           datetime.now()).strftime("%Y-%m-%d")
            post = search_historical(client, username, repo_id, post_start, post_end)
            db.upsert_mobility({
                "username": username,
                "home_repo": repo_id,
                "home_contributions": contribs,
                "external_repos": post["external_repos"],
                "external_commits": post["external_commits"],
                "external_prs": post["external_prs"],
                "external_issues": post["external_issues"],
                "external_repos_list": json.dumps(
                    post["external_repos_list"], ensure_ascii=False),
                "period": "post_ai",
                "period_start": post_start,
                "period_end": post_end,
            })

        analyzed += 1
        # 保存断点：记录当前完成的贡献者
        if resume:
            db.save_checkpoint("m2_mobility", repo_id, "completed_contributors",
                               f"{len(completed) + analyzed}")
        if analyzed % 10 == 0:
            logger.info(f"  已分析 {analyzed}/{len(contributors)} (跳过 {skipped} 个已有)")

    # 采集完成，清除断点
    if resume:
        db.clear_checkpoint("m2_mobility", repo_id)

    db.log("m2_mobility", repo_id, "complete", count=analyzed,
           message=f"analyzed {analyzed}, skipped {skipped}")
    logger.info(f"[M2] {repo_id}: 完成，分析 {analyzed} 个贡献者 (跳过 {skipped} 个已有)")
    return analyzed
