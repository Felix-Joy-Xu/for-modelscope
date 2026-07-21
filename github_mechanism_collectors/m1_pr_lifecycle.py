"""
M1 采集器：PR 生命周期与审查负担指标
对应论文 M1（生成→审查的注意力迁移）

采集指标：
  - PR 从提交到合并的周期（小时）
  - review comment 数量与退回修改轮次
  - AI 生成代码标签与 review 密度的相关性
  - 前后对比：AI 工具引入前12月 vs 引入后12月
"""

import json
import re
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional

from github_api import GitHubClient
from database import MechanismDB
from config import (
    M1_AI_LABELS, M1_AI_KEYWORDS, M3_BOT_PATTERNS,
    M3_VISIBILITY_KEYWORDS, MAX_PRS_PER_REPO,
    LOOKBACK_MONTHS, LOOKAHEAD_MONTHS,
)

logger = logging.getLogger(__name__)


def is_bot_user(username: str) -> bool:
    """判断用户名是否为 bot。"""
    if not username:
        return False
    name_lower = username.lower()
    for pattern in M3_BOT_PATTERNS:
        if pattern in name_lower:
            return True
    if name_lower.endswith("[bot]") or name_lower.endswith("-bot"):
        return True
    return False


def detect_ai_signals(pr: dict) -> dict:
    """
    检测 PR 中的 AI 相关信号。
    返回: {"has_label": bool, "has_keyword": bool, "signals": [str]}
    """
    signals = []

    # 检查标签
    labels = [lbl.get("name", "").lower() for lbl in pr.get("labels", [])]
    has_label = any(
        ai_lbl in label
        for label in labels
        for ai_lbl in M1_AI_LABELS
    )
    if has_label:
        matched = [l for l in labels if any(a in l for a in M1_AI_LABELS)]
        signals.extend([f"label:{l}" for l in matched])

    # 检查标题和描述中的关键词
    title = (pr.get("title") or "").lower()
    body = (pr.get("body") or "").lower()
    text = f"{title} {body}"
    has_keyword = False
    for kw in M1_AI_KEYWORDS:
        if kw in text:
            has_keyword = True
            signals.append(f"keyword:{kw}")

    return {
        "has_label": has_label,
        "has_keyword": has_keyword,
        "signals": signals,
    }


def compute_cycle_hours(created_at: str, merged_at: Optional[str]) -> Optional[float]:
    """计算 PR 从创建到合并的小时数。"""
    if not merged_at:
        return None
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        merged = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        delta = merged - created
        return round(delta.total_seconds() / 3600, 2)
    except (ValueError, TypeError):
        return None


def determine_period(date_str: str, ai_adoption_date: str) -> str:
    """判断日期属于 pre_ai 还是 post_ai。"""
    if not date_str or not ai_adoption_date:
        return "unknown"
    try:
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
        adoption = datetime.fromisoformat(ai_adoption_date)
        return "post_ai" if date >= adoption else "pre_ai"
    except (ValueError, TypeError):
        return "unknown"


def get_time_window(ai_adoption_date: str) -> tuple:
    """返回采集的时间窗口 (start, end)。"""
    adoption = datetime.fromisoformat(ai_adoption_date)
    start = adoption - relativedelta(months=LOOKBACK_MONTHS)
    end = adoption + relativedelta(months=LOOKAHEAD_MONTHS)
    return start.isoformat(), min(end, datetime.now()).isoformat()


def collect_pr_reviews_detail(
    client: GitHubClient, owner: str, repo: str, pr_number: int
) -> dict:
    """
    获取 PR 的详细 review 信息，并计算：
      - review_rounds: review 轮次
      - changes_requested: 退回修改次数
      - approvals: 批准次数
      - unique_reviewers: 独立 reviewer 数
      - bot_reviews: bot 发出的 review 数
      - visibility_keywords: 合规/可见性关键词
    """
    reviews = client.get_pull_reviews(owner, repo, pr_number)
    comments = client.get_pull_comments(owner, repo, pr_number)

    changes_requested = 0
    approvals = 0
    reviewers = set()
    bot_reviews = 0
    visibility_kw_found = []

    for review in reviews:
        state = review.get("state", "")
        user = review.get("user", {}).get("login", "")

        if is_bot_user(user):
            bot_reviews += 1
        else:
            reviewers.add(user)

        if state == "CHANGES_REQUESTED":
            changes_requested += 1
        elif state == "APPROVED":
            approvals += 1

        # 检查 review body 中的可见性关键词
        body = (review.get("body") or "").lower()
        for kw in M3_VISIBILITY_KEYWORDS:
            if kw.lower() in body:
                visibility_kw_found.append(kw)

    # 统计行内评论
    bot_comments = 0
    for comment in comments:
        user = comment.get("user", {}).get("login", "")
        if is_bot_user(user):
            bot_comments += 1

        body = (comment.get("body") or "").lower()
        for kw in M3_VISIBILITY_KEYWORDS:
            if kw.lower() in body:
                visibility_kw_found.append(kw)

    # Review 轮次 = CHANGES_REQUESTED + APPROVED 的总数
    # （每次正式审查视为一轮）
    review_rounds = len([
        r for r in reviews
        if r.get("state") in ("CHANGES_REQUESTED", "APPROVED", "COMMENTED")
        and not is_bot_user(r.get("user", {}).get("login", ""))
    ])

    return {
        "review_comments": len(comments),
        "review_rounds": review_rounds,
        "changes_requested": changes_requested,
        "approvals": approvals,
        "unique_reviewers": len(reviewers),
        "bot_reviews": bot_reviews,
        "bot_comments": bot_comments,
        "visibility_keywords": list(set(visibility_kw_found)),
    }


def collect_m1_for_repo(
    client: GitHubClient, db: MechanismDB,
    owner: str, repo: str, repo_config: dict,
    collect_review_detail: bool = True,
):
    """
    对单个仓库采集 M1（PR 生命周期）数据。

    Args:
        client: GitHub API 客户端
        db: 数据库实例
        owner, repo: 仓库标识
        repo_config: 仓库配置（含 ai_adoption_date, org_type）
        collect_review_detail: 是否采集每个 PR 的 review 详情
                              （True 时 API 消耗量大幅增加）
    """
    repo_id = f"{owner}/{repo}"
    ai_date = repo_config["ai_adoption_date"]
    start_date, end_date = get_time_window(ai_date)

    logger.info(f"[M1] 开始采集 {repo_id} 的 PR 生命周期数据")
    logger.info(f"  时间窗口: {start_date} → {end_date}")
    logger.info(f"  AI 引入日期: {ai_date}")

    db.log(repo_id, "M1", "start",
           message=f"时间窗口 {start_date} → {end_date}")

    collected = 0
    skipped = 0
    batch = []

    for pr in client.get_pulls(owner, repo, state="all", max_items=MAX_PRS_PER_REPO):
        pr_created = pr.get("created_at", "")

        # 过滤时间窗口外的 PR
        if pr_created < start_date:
            # PR 按时间倒序排列，早于窗口的可以停止
            break
        if pr_created > end_date:
            skipped += 1
            continue

        pr_number = pr["number"]
        ai_info = detect_ai_signals(pr)
        period = determine_period(pr_created, ai_date)

        # 基础记录
        record = {
            "repo_id": repo_id,
            "pr_number": pr_number,
            "title": pr.get("title", ""),
            "state": "merged" if pr.get("merged_at") else pr.get("state", ""),
            "author": pr.get("user", {}).get("login", ""),
            "author_is_bot": int(is_bot_user(pr.get("user", {}).get("login", ""))),
            "created_at": pr_created,
            "merged_at": pr.get("merged_at"),
            "closed_at": pr.get("closed_at"),
            "cycle_hours": compute_cycle_hours(pr_created, pr.get("merged_at")),
            "review_comments": pr.get("review_comments", 0),
            "general_comments": pr.get("comments", 0),
            "has_ai_label": int(ai_info["has_label"]),
            "has_ai_keyword": int(ai_info["has_keyword"]),
            "ai_signals": json.dumps(ai_info["signals"], ensure_ascii=False),
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "changed_files": pr.get("changed_files", 0),
            "period": period,
            # 默认值，可能被 review detail 覆盖
            "review_rounds": 0,
            "changes_requested": 0,
            "approvals": 0,
            "unique_reviewers": 0,
            "commits_count": 0,
        }

        # 采集 review 详情（API 密集操作）
        if collect_review_detail:
            try:
                detail = collect_pr_reviews_detail(client, owner, repo, pr_number)
                record["review_comments"] = detail["review_comments"]
                record["review_rounds"] = detail["review_rounds"]
                record["changes_requested"] = detail["changes_requested"]
                record["approvals"] = detail["approvals"]
                record["unique_reviewers"] = detail["unique_reviewers"]

                # 同时写入 M3 可见性数据
                m3_record = {
                    "repo_id": repo_id,
                    "pr_number": pr_number,
                    "bot_comments": detail["bot_comments"],
                    "bot_reviews": detail["bot_reviews"],
                    "automated_checks": detail["bot_comments"] + detail["bot_reviews"],
                    "bot_usernames": json.dumps([], ensure_ascii=False),
                    "visibility_keywords_count": len(detail["visibility_keywords"]),
                    "visibility_keywords_found": json.dumps(
                        detail["visibility_keywords"], ensure_ascii=False
                    ),
                    "period": period,
                }
                db.insert_pr_visibility(m3_record)

            except Exception as e:
                logger.warning(f"  PR #{pr_number} review 详情采集失败: {e}")

        # 获取 commit 数
        try:
            commits = client.get_pull_commits(owner, repo, pr_number)
            record["commits_count"] = len(commits)
        except Exception:
            pass

        batch.append(record)
        collected += 1

        if collected % 50 == 0:
            logger.info(f"  已采集 {collected} 个 PR...")
            db.batch_insert_pr_lifecycle(batch)
            batch = []

    # 写入剩余批次
    if batch:
        db.batch_insert_pr_lifecycle(batch)

    db.log(repo_id, "M1", "complete", items=collected,
           message=f"采集 {collected} 个 PR，跳过 {skipped} 个")
    logger.info(f"[M1] {repo_id} 完成: 采集 {collected} 个 PR")

    return collected
