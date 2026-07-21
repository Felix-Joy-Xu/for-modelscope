"""
M4 采集器：问责—权力鸿沟话语编码
对应论文 M4（问责—权力鸿沟）

采集指标：
  - Issue 中 AI 生成代码引发 bug 后的责任归因话语
  - committer vs reviewer 的话语博弈模式
  - 事故追溯帖中个体化归因的话语频率
"""

import json
import re
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Optional

from github_api import GitHubClient
from database import MechanismDB
from config import (
    M4_ACCOUNTABILITY_KEYWORDS, M4_BUG_LABELS,
    MAX_ISSUES_PER_REPO, LOOKBACK_MONTHS, LOOKAHEAD_MONTHS,
)
from collectors.m1_pr_lifecycle import determine_period, is_bot_user

logger = logging.getLogger(__name__)


def extract_context(text: str, keyword: str, context_chars: int = 150) -> str:
    """提取关键词前后的上下文文本。"""
    text_lower = text.lower()
    kw_lower = keyword.lower()
    pos = text_lower.find(kw_lower)
    if pos == -1:
        return ""
    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(keyword) + context_chars)
    context = text[start:end]
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."
    return context


def code_discourse(text: str) -> Dict[str, List[dict]]:
    """
    对文本进行话语编码，返回各类别匹配结果。

    返回: {
        "individual_blame": [{"keyword": "...", "context": "..."}, ...],
        "ai_attribution": [...],
        "systemic_attribution": [...],
        "accountability_gap": [...],
    }
    """
    if not text:
        return {cat: [] for cat in M4_ACCOUNTABILITY_KEYWORDS}

    text_lower = text.lower()
    results = {}

    for category, keywords in M4_ACCOUNTABILITY_KEYWORDS.items():
        matches = []
        for kw in keywords:
            if kw.lower() in text_lower:
                context = extract_context(text, kw)
                matches.append({
                    "keyword": kw,
                    "context": context,
                })
        results[category] = matches

    return results


def is_bug_issue(issue: dict) -> bool:
    """判断 issue 是否为 bug 类型。"""
    labels = [lbl.get("name", "").lower() for lbl in issue.get("labels", [])]
    for label in labels:
        for bug_label in M4_BUG_LABELS:
            if bug_label in label:
                return True
    # 也检查标题中的 bug 关键词
    title = (issue.get("title") or "").lower()
    bug_title_kw = ["bug", "crash", "broken", "regression", "fix", "error", "failure"]
    return any(kw in title for kw in bug_title_kw)


def collect_m4_for_repo(
    client: GitHubClient, db: MechanismDB,
    owner: str, repo: str, repo_config: dict,
    bug_only: bool = False,
):
    """
    对单个仓库采集 M4（问责话语）数据。

    Args:
        client: GitHub API 客户端
        db: 数据库实例
        owner, repo: 仓库标识
        repo_config: 仓库配置
        bug_only: 是否只采集 bug 类 issue
    """
    repo_id = f"{owner}/{repo}"
    ai_date = repo_config["ai_adoption_date"]

    # 计算时间窗口
    adoption = datetime.fromisoformat(ai_date)
    start_date = (adoption - relativedelta(months=LOOKBACK_MONTHS)).isoformat()
    end_date = min(
        adoption + relativedelta(months=LOOKAHEAD_MONTHS),
        datetime.now()
    ).isoformat()

    logger.info(f"[M4] 开始采集 {repo_id} 的问责话语数据")
    logger.info(f"  时间窗口: {start_date} → {end_date}")
    logger.info(f"  仅 bug 类: {bug_only}")

    db.log(repo_id, "M4", "start",
           message=f"bug_only={bug_only}")

    collected = 0
    discourse_total = 0

    # 获取 issues
    issues_iter = client.get_issues(
        owner, repo, state="all", max_items=MAX_ISSUES_PER_REPO
    )

    for issue in issues_iter:
        issue_created = issue.get("created_at", "")

        # 时间窗口过滤
        if issue_created < start_date:
            break
        if issue_created > end_date:
            continue

        # Bug 过滤
        is_bug = is_bug_issue(issue)
        if bug_only and not is_bug:
            continue

        issue_number = issue["number"]
        period = determine_period(issue_created, ai_date)

        # 获取所有评论
        try:
            comments = client.get_issue_comments(owner, repo, issue_number)
        except Exception as e:
            logger.warning(f"  Issue #{issue_number} 评论采集失败: {e}")
            comments = []

        # 合并所有文本进行话语编码
        all_text_parts = [
            issue.get("title", ""),
            issue.get("body") or "",
        ]
        for c in comments:
            all_text_parts.append(c.get("body") or "")

        # 对 issue 整体进行话语编码
        full_text = "\n".join(all_text_parts)
        discourse = code_discourse(full_text)

        # 计数
        individual_count = len(discourse["individual_blame"])
        ai_count = len(discourse["ai_attribution"])
        systemic_count = len(discourse["systemic_attribution"])
        gap_count = len(discourse["accountability_gap"])
        total_matches = individual_count + ai_count + systemic_count + gap_count

        # 统计参与者
        commenters = set()
        for c in comments:
            user = c.get("user", {}).get("login", "")
            if user and not is_bot_user(user):
                commenters.add(user)

        # 保存 issue 级记录
        labels_json = json.dumps(
            [lbl.get("name") for lbl in issue.get("labels", [])],
            ensure_ascii=False
        )

        record = {
            "repo_id": repo_id,
            "issue_number": issue_number,
            "title": issue.get("title", ""),
            "state": issue.get("state", ""),
            "author": issue.get("user", {}).get("login", ""),
            "is_bug": int(is_bug),
            "labels": labels_json,
            "created_at": issue_created,
            "closed_at": issue.get("closed_at"),
            "comments_count": len(comments),
            "individual_blame_count": individual_count,
            "ai_attribution_count": ai_count,
            "systemic_attribution_count": systemic_count,
            "accountability_gap_count": gap_count,
            "discourse_matches": json.dumps(
                {k: [m["keyword"] for m in v] for k, v in discourse.items()},
                ensure_ascii=False
            ),
            "unique_commenters": len(commenters),
            "committer_vs_reviewer": json.dumps({}, ensure_ascii=False),
            "period": period,
        }
        db.insert_issue_discourse(record)

        # 保存话语片段明细（用于定性分析）
        if total_matches > 0:
            # 对每条评论分别编码并保存片段
            for c in comments:
                comment_body = c.get("body") or ""
                comment_discourse = code_discourse(comment_body)
                for disc_type, matches in comment_discourse.items():
                    for match in matches:
                        snippet = {
                            "repo_id": repo_id,
                            "issue_number": issue_number,
                            "comment_id": c.get("id"),
                            "author": c.get("user", {}).get("login", ""),
                            "created_at": c.get("created_at", ""),
                            "discourse_type": disc_type,
                            "matched_keyword": match["keyword"],
                            "context_text": match["context"],
                            "full_comment": comment_body[:2000],  # 截断保存
                        }
                        db.insert_discourse_snippet(snippet)
                        discourse_total += 1

            # 也对 issue body 本身编码
            body_discourse = code_discourse(issue.get("body") or "")
            for disc_type, matches in body_discourse.items():
                for match in matches:
                    snippet = {
                        "repo_id": repo_id,
                        "issue_number": issue_number,
                        "comment_id": None,
                        "author": issue.get("user", {}).get("login", ""),
                        "created_at": issue_created,
                        "discourse_type": disc_type,
                        "matched_keyword": match["keyword"],
                        "context_text": match["context"],
                        "full_comment": (issue.get("body") or "")[:2000],
                    }
                    db.insert_discourse_snippet(snippet)
                    discourse_total += 1

        collected += 1

        if collected % 100 == 0:
            logger.info(f"  已采集 {collected} 个 Issue，{discourse_total} 条话语片段...")

    db.log(repo_id, "M4", "complete", items=collected,
           message=f"采集 {collected} 个 Issue，{discourse_total} 条话语片段")
    logger.info(
        f"[M4] {repo_id} 完成: {collected} 个 Issue，"
        f"{discourse_total} 条话语片段"
    )

    return collected
