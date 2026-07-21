"""
M4 话语编码：对现有 github_threads.db 的 83,690 条评论进行机制化编码
============================================================================
这是一个「免费」的分析步骤 —— 不需要任何 API 调用，
直接读取你已有的 github_threads.db，按 M4 问责话语框架进行关键词编码。

对应论文:
  M4（问责—权力鸿沟）：个体化归因 / AI归因 / 系统归因 / 问责鸿沟
  M1 补充：工作流转变叙事
  H2 补充：技能焦虑叙事

输出:
  - m4_coded_comments 表：每条评论的各类别匹配计数
  - m4_snippets 表：匹配到的话语片段明细（可直接用于论文引证）
"""

import sqlite3
import json
import logging
import os
from datetime import datetime

from supplement_db import SupplementDB
from supplement_config import (
    EXISTING_THREADS_DB, SUPPLEMENT_DB, DISCOURSE_KEYWORDS, TARGET_REPOS,
)

logger = logging.getLogger(__name__)


def extract_context(text: str, keyword: str, chars: int = 150) -> str:
    """提取关键词周围的上下文。"""
    pos = text.lower().find(keyword.lower())
    if pos == -1:
        return ""
    start = max(0, pos - chars)
    end = min(len(text), pos + len(keyword) + chars)
    ctx = text[start:end]
    if start > 0:
        ctx = "..." + ctx
    if end < len(text):
        ctx = ctx + "..."
    return ctx


def code_text(text: str) -> dict:
    """
    对文本进行话语编码。
    返回: {category: [{"keyword": str, "context": str}]}
    """
    if not text:
        return {cat: [] for cat in DISCOURSE_KEYWORDS}

    text_lower = text.lower()
    results = {}
    for category, keywords in DISCOURSE_KEYWORDS.items():
        matches = []
        for kw in keywords:
            if kw.lower() in text_lower:
                matches.append({
                    "keyword": kw,
                    "context": extract_context(text, kw),
                })
        results[category] = matches
    return results


# ---- 仓库 AI 集成深度分类（横截面比较用） ----
# 替代原来的时间分期（pre_ai / post_ai），因为数据主要集中在 2024-2026 年，
# 无法做有意义的 AI 前后对比。
#
# 分类标准：
#   "ai_native"    — AI 原生工具（如 cline/cline），本身就是 AI 编程助手
#   "ai_deep"      — 深度集成 AI 的仓库（如 oven-sh/bun 使用大量 bot/自动化）
#   "ai_moderate"  — 中等 AI 集成（如 microsoft/vscode 有 Copilot 但非核心）
#   "ai_light"     — 轻度 AI 使用（传统开源项目，AI 非核心工作流）
#   "unknown"      — 无法分类

REPO_AI_CLASSIFICATION = {
    "cline/cline":          "ai_native",      # AI 编程助手本身
    "oven-sh/bun":          "ai_deep",        # 大量 bot PR、AI 自动化
    "microsoft/vscode":     "ai_moderate",    # 有 Copilot 但仓库本身非 AI
    "vercel/next.js":       "ai_moderate",    # Vercel 有 AI 产品但仓库传统
    "alibaba/nacos":        "ai_light",       # 中国大厂，AI 集成较浅
    "pingcap/tidb":         "ai_light",       # 中国中型项目，AI 使用有限
    "nodejs/node":          "ai_light",       # 社区基础设施，保守
    "facebook/react":       "ai_light",       # 大厂但仓库本身传统
    "tencent/tdesign":      "ai_light",
    "withastro/astro":      "ai_moderate",
    "alibaba/dubbo":        "ai_light",
    "angular/angular":      "ai_moderate",
    "bytedance/monoio":     "ai_light",
}


def determine_period(created_at: str, repo_id: str) -> str:
    """
    根据仓库 AI 集成深度返回横截面分类标签。
    
    注意：不再使用时间分期（pre_ai/post_ai），因为数据主要集中在 2024-2026 年，
    AI 分界线（2023-06）之前的数据极少（仅 24 条），无法做有意义的对比。
    
    改用仓库间的横截面比较：按 AI 集成深度分类。
    """
    return REPO_AI_CLASSIFICATION.get(repo_id, "unknown")


def code_existing_threads(db: SupplementDB, threads_db_path: str = None):
    """
    对现有 github_threads.db 中的所有评论进行话语编码。

    流程:
      1. 读取 threads 表 → 编码 thread body
      2. 读取 comments 表 → 编码 comment body
      3. 结果写入 supplement_data.db 的 m4_coded_comments 和 m4_snippets
    """
    src_path = threads_db_path or EXISTING_THREADS_DB
    if not os.path.exists(src_path):
        logger.error(f"源数据库不存在: {src_path}")
        return 0

    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row

    # 统计
    total_threads = src.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
    total_comments = src.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    logger.info(f"[M4编码] 开始: {total_threads} threads + {total_comments} comments")
    db.log("m4_coding", "all", "start",
           message=f"{total_threads} threads + {total_comments} comments")

    coded_count = 0
    snippet_count = 0
    batch_coded = []
    batch_snippets = []
    BATCH_SIZE = 500

    # ---- 1. 编码 thread bodies ----
    logger.info("[M4编码] 阶段1: 编码 thread bodies...")
    cursor = src.execute("""
        SELECT thread_id, source_owner || '/' || source_repo as repo_id,
               title, body, author, created_at, url
        FROM threads
    """)

    for row in cursor:
        thread_id = row["thread_id"]
        repo_id = row["repo_id"]
        text = f"{row['title'] or ''}\n{row['body'] or ''}"
        coded = code_text(text)

        # 计数
        counts = {cat: len(matches) for cat, matches in coded.items()}
        total_hits = sum(counts.values())

        record = {
            "source_db": "github_threads.db",
            "thread_id": thread_id,
            "comment_id": "thread_body",
            "repo_id": repo_id,
            "author": row["author"],
            "created_at": row["created_at"],
            "text_length": len(text),
            "individual_blame": counts.get("individual_blame", 0),
            "ai_attribution": counts.get("ai_attribution", 0),
            "systemic_attribution": counts.get("systemic_attribution", 0),
            "accountability_gap": counts.get("accountability_gap", 0),
            "workflow_shift": counts.get("workflow_shift", 0),
            "skill_anxiety": counts.get("skill_anxiety", 0),
            "matched_keywords": json.dumps(
                {c: [m["keyword"] for m in ms] for c, ms in coded.items() if ms},
                ensure_ascii=False
            ),
            "period": determine_period(row["created_at"], repo_id),
        }
        batch_coded.append(record)

        # 保存片段
        if total_hits > 0:
            for cat, matches in coded.items():
                for m in matches:
                    batch_snippets.append({
                        "thread_id": thread_id,
                        "comment_id": "thread_body",
                        "repo_id": repo_id,
                        "author": row["author"],
                        "created_at": row["created_at"],
                        "category": cat,
                        "keyword": m["keyword"],
                        "context": m["context"],
                        "url": row["url"] or "",
                    })
                    snippet_count += 1

        coded_count += 1
        if len(batch_coded) >= BATCH_SIZE:
            db.batch_upsert_coded(batch_coded)
            db.batch_insert_snippets(batch_snippets)
            batch_coded = []
            batch_snippets = []
            if coded_count % 2000 == 0:
                logger.info(f"  已编码 {coded_count} 条...")

    # ---- 2. 编码 comments ----
    logger.info("[M4编码] 阶段2: 编码 comments...")
    cursor = src.execute("""
        SELECT c.thread_id, c.comment_id, c.author, c.body, c.created_at,
               t.source_owner || '/' || t.source_repo as repo_id,
               t.url as thread_url
        FROM comments c
        JOIN threads t ON c.thread_id = t.thread_id
    """)

    comment_count = 0
    for row in cursor:
        text = row["body"] or ""
        if not text.strip():
            continue

        coded = code_text(text)
        counts = {cat: len(matches) for cat, matches in coded.items()}
        total_hits = sum(counts.values())

        record = {
            "source_db": "github_threads.db",
            "thread_id": row["thread_id"],
            "comment_id": str(row["comment_id"]),
            "repo_id": row["repo_id"],
            "author": row["author"],
            "created_at": row["created_at"],
            "text_length": len(text),
            "individual_blame": counts.get("individual_blame", 0),
            "ai_attribution": counts.get("ai_attribution", 0),
            "systemic_attribution": counts.get("systemic_attribution", 0),
            "accountability_gap": counts.get("accountability_gap", 0),
            "workflow_shift": counts.get("workflow_shift", 0),
            "skill_anxiety": counts.get("skill_anxiety", 0),
            "matched_keywords": json.dumps(
                {c: [m["keyword"] for m in ms] for c, ms in coded.items() if ms},
                ensure_ascii=False
            ),
            "period": determine_period(row["created_at"], row["repo_id"]),
        }
        batch_coded.append(record)

        if total_hits > 0:
            for cat, matches in coded.items():
                for m in matches:
                    batch_snippets.append({
                        "thread_id": row["thread_id"],
                        "comment_id": str(row["comment_id"]),
                        "repo_id": row["repo_id"],
                        "author": row["author"],
                        "created_at": row["created_at"],
                        "category": cat,
                        "keyword": m["keyword"],
                        "context": m["context"],
                        "url": row["thread_url"] or "",
                    })
                    snippet_count += 1

        comment_count += 1
        coded_count += 1

        if len(batch_coded) >= BATCH_SIZE:
            db.batch_upsert_coded(batch_coded)
            db.batch_insert_snippets(batch_snippets)
            batch_coded = []
            batch_snippets = []
            if comment_count % 10000 == 0:
                logger.info(f"  已编码 {comment_count}/{total_comments} 条评论...")

    # 最后一批
    if batch_coded:
        db.batch_upsert_coded(batch_coded)
    if batch_snippets:
        db.batch_insert_snippets(batch_snippets)

    src.close()

    db.log("m4_coding", "all", "complete", count=coded_count,
           message=f"编码 {coded_count} 条，提取 {snippet_count} 条话语片段")
    logger.info(f"[M4编码] 完成: 编码 {coded_count} 条，提取 {snippet_count} 条话语片段")

    return coded_count
