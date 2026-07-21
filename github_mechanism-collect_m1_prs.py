"""
M1 补充采集：PR 结构化生命周期指标
============================================
从 GitHub API 新采集以下指标（现有 github_threads.db 不含）：
  - PR 从创建到合并的周期（cycle_hours）
  - review comment 数量、review 轮次、退回修改次数
  - AI 生成代码标签与 review 密度的关系
  - bot/自动化检查的介入频率（M3 附带）

对应论文:
  M1（注意力迁移）行为印证：PR 合并周期、review 密度
  H1（验证疲劳）可证伪条件：AI 参与度与全局效率感知的关系
  M3（过程可见性）附带采集：bot 评论/review 频率
"""

import json
import logging
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

from github_api import GitHubClient
from supplement_db import SupplementDB
from supplement_config import (
    TARGET_REPOS, AI_LABELS, AI_KEYWORDS, BOT_PATTERNS,
    M1_MAX_PRS_PER_REPO, M1_LOOKBACK_MONTHS, M1_LOOKAHEAD_MONTHS,
    M1_COLLECT_REVIEW_DETAIL,
)

logger = logging.getLogger(__name__)


# ---- 工具函数 ----

def is_bot(username: str) -> bool:
    if not username:
        return False
    name = username.lower()
    if name.endswith("[bot]") or name.endswith("-bot"):
        return True
    return any(p in name for p in BOT_PATTERNS)


def detect_ai(pr: dict) -> dict:
    """检测 PR 中的 AI 参与信号。"""
    signals = []

    labels = [l.get("name", "").lower() for l in pr.get("labels", [])]
    has_label = any(ai in lab for lab in labels for ai in AI_LABELS)
    if has_label:
        signals.extend(f"label:{l}" for l in labels if any(a in l for a in AI_LABELS))

    text = f"{(pr.get('title') or '').lower()} {(pr.get('body') or '').lower()}"
    has_kw = False
    for kw in AI_KEYWORDS:
        if kw in text:
            has_kw = True
            signals.append(f"kw:{kw}")

    return {"has_label": has_label, "has_keyword": has_kw, "signals": signals}


def cycle_hours(created: str, merged: str) -> float:
    if not merged:
        return None
    try:
        c = datetime.fromisoformat(created.replace("Z", "+00:00"))
        m = datetime.fromisoformat(merged.replace("Z", "+00:00"))
        return round((m - c).total_seconds() / 3600, 2)
    except (ValueError, TypeError):
        return None


def period_of(date_str: str, ai_date: str) -> str:
    if not date_str or not ai_date:
        return "unknown"
    try:
        d = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
        a = datetime.fromisoformat(ai_date)
        return "post_ai" if d >= a else "pre_ai"
    except (ValueError, TypeError):
        return "unknown"


def time_window(ai_date: str) -> tuple:
    a = datetime.fromisoformat(ai_date)
    start = a - relativedelta(months=M1_LOOKBACK_MONTHS)
    if M1_LOOKAHEAD_MONTHS > 0:
        end = min(a + relativedelta(months=M1_LOOKAHEAD_MONTHS), datetime.now())
    else:
        end = datetime.now()  # 0 = 延伸到当前时间
    return start.isoformat(), end.isoformat()


# ---- review 详情采集 ----

def fetch_review_detail(client: GitHubClient, owner: str, repo: str, pr_num: int) -> dict:
    """采集单个 PR 的 review 详情。"""
    reviews = list(client.get_paginated(f"/repos/{owner}/{repo}/pulls/{pr_num}/reviews"))
    comments = list(client.get_paginated(f"/repos/{owner}/{repo}/pulls/{pr_num}/comments"))

    changes_req = 0
    approvals = 0
    reviewers = set()
    bot_revs = 0
    rounds = 0
    bot_cmts = 0

    for r in reviews:
        user = r.get("user", {}).get("login", "")
        state = r.get("state", "")
        if is_bot(user):
            bot_revs += 1
        else:
            reviewers.add(user)
            if state in ("CHANGES_REQUESTED", "APPROVED", "COMMENTED"):
                rounds += 1
        if state == "CHANGES_REQUESTED":
            changes_req += 1
        elif state == "APPROVED":
            approvals += 1

    for c in comments:
        if is_bot(c.get("user", {}).get("login", "")):
            bot_cmts += 1

    return {
        "review_comments": len(comments),
        "review_rounds": rounds,
        "changes_requested": changes_req,
        "approvals": approvals,
        "unique_reviewers": len(reviewers),
        "bot_reviews": bot_revs,
        "bot_comments": bot_cmts,
    }


# ---- 主采集逻辑 ----

def collect_prs_for_repo(
    client: GitHubClient, db: SupplementDB,
    repo_id: str, config: dict,
    with_review_detail: bool = True,
    resume: bool = False,
):
    """
    对单个仓库采集 PR 结构化生命周期数据。

    支持断点续传：如果 resume=True，会从已采集的最大 PR 编号之后继续。

    API 消耗估算:
      - 无 review 详情: ~N/100 次请求（N = PR 数）
      - 有 review 详情: ~N*3 次请求（每个 PR 额外 2 次调用）
    """
    owner, repo = repo_id.split("/")
    ai_date = config["ai_adoption_date"]
    start, end = time_window(ai_date)

    logger.info(f"[M1] {repo_id}: 开始采集 PR 结构化数据")
    logger.info(f"  时间窗口: {start[:10]} → {end[:10]}, AI分界: {ai_date}")

    existing = db.get_pr_count(repo_id)
    if existing > 0:
        logger.info(f"  已有 {existing} 条 PR 数据")

    # ---- 断点续传：获取已采集的最大 PR 编号 ----
    last_pr = 0
    if resume:
        last_pr = db.get_last_pr_number(repo_id)
        if last_pr > 0:
            logger.info(f"  断点续传模式：已采集到 PR #{last_pr}，将从其后继续")
        else:
            logger.info(f"  断点续传模式：无已有数据，从头开始")

    db.log("m1_pr", repo_id, "start",
           message=f"window={start[:10]}~{end[:10]}, resume={resume}, last_pr={last_pr}")

    collected = 0
    batch = []
    skipped = 0

    for pr in client.get_pulls(owner, repo, state="all",
                                max_items=M1_MAX_PRS_PER_REPO):
        created = pr.get("created_at", "")

        # 时间窗口过滤
        if created < start:
            break  # 按时间倒序，早于窗口则停止
        if created > end:
            continue

        pr_num = pr["number"]

        # ---- 断点续传：跳过已采集的 PR ----
        if resume and pr_num <= last_pr:
            skipped += 1
            continue

        ai = detect_ai(pr)
        per = period_of(created, ai_date)

        record = {
            "repo_id": repo_id,
            "pr_number": pr_num,
            "title": pr.get("title", ""),
            "state": "merged" if pr.get("merged_at") else pr.get("state", ""),
            "author": pr.get("user", {}).get("login", ""),
            "author_is_bot": int(is_bot(pr.get("user", {}).get("login", ""))),
            "created_at": created,
            "merged_at": pr.get("merged_at"),
            "closed_at": pr.get("closed_at"),
            "cycle_hours": cycle_hours(created, pr.get("merged_at")),
            "review_comments": pr.get("review_comments", 0),
            "general_comments": pr.get("comments", 0),
            "review_rounds": 0,
            "changes_requested": 0,
            "approvals": 0,
            "unique_reviewers": 0,
            "commits_count": 0,
            "has_ai_label": int(ai["has_label"]),
            "has_ai_keyword": int(ai["has_keyword"]),
            "ai_signals": json.dumps(ai["signals"], ensure_ascii=False),
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
            "changed_files": pr.get("changed_files", 0),
            "bot_comments": 0,
            "bot_reviews": 0,
            "period": per,
        }

        # review 详情
        if with_review_detail:
            try:
                detail = fetch_review_detail(client, owner, repo, pr_num)
                record.update({
                    "review_comments": detail["review_comments"],
                    "review_rounds": detail["review_rounds"],
                    "changes_requested": detail["changes_requested"],
                    "approvals": detail["approvals"],
                    "unique_reviewers": detail["unique_reviewers"],
                    "bot_comments": detail["bot_comments"],
                    "bot_reviews": detail["bot_reviews"],
                })
            except Exception as e:
                logger.warning(f"  PR #{pr_num} review 详情失败: {e}")

        # commit 数
        try:
            commits = list(client.get_paginated(
                f"/repos/{owner}/{repo}/pulls/{pr_num}/commits"
            ))
            record["commits_count"] = len(commits)
        except Exception:
            pass

        batch.append(record)
        collected += 1

        if collected % 50 == 0:
            db.batch_upsert_prs(batch)
            batch = []
            # 保存断点：记录当前批次的最大 PR 编号
            if resume:
                db.save_checkpoint("m1_pr", repo_id, "last_pr_number", str(pr_num))
            logger.info(f"  已采集 {collected} 个 PR (跳过 {skipped} 个已有, API调用: {client.request_count})")

    if batch:
        db.batch_upsert_prs(batch)
        if resume:
            db.save_checkpoint("m1_pr", repo_id, "last_pr_number", str(pr_num))

    # 采集完成，清除断点
    if resume:
        db.clear_checkpoint("m1_pr", repo_id)

    db.log("m1_pr", repo_id, "complete", count=collected,
           message=f"{collected} PRs, skipped {skipped}, API calls: {client.request_count}")
    logger.info(f"[M1] {repo_id}: 完成，共 {collected} 个 PR (跳过 {skipped} 个已有)")

    return collected
