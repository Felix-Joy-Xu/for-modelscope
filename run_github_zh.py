#!/usr/bin/env python3
"""GitHub 中文关键词全量采集（仅 Issue）- 慢速稳定版"""
import os
import time
import random

if 'MONGO_URI' not in os.environ:
    os.environ['MONGO_URI'] = 'mongodb://localhost:27017/coding_labor'

import requests
from crawler import (
    DatabaseManager, GitHubCrawler, KEYWORDS_ZH, logger,
    PHASE_A_START, PHASE_A_END, PHASE_B_START, PHASE_B_END,
    req_manager
)

logger.info("=" * 60)
logger.info("GitHub Chinese Keywords Crawl (Issue Only) - Slow Mode")
logger.info("=" * 60)

db = DatabaseManager(os.environ['MONGO_URI'], "coding_labor")

tokens = [t for t in [
    os.environ.get('GITHUB_TOKEN_1', ''),
    os.environ.get('GITHUB_TOKEN_2', ''),
    os.environ.get('GITHUB_TOKEN_3', ''),
] if t]

gh = GitHubCrawler(tokens, db)

# 中文关键词配置
KEYWORDS = KEYWORDS_ZH  # 全部中文关键词
MAX_PAGES = 10          # 每关键词采 10 页（每页 50 条）

# 硬编码已完成的 Phase A 关键词（从日志中确认）
# 这些关键词的数据已通过 MongoDB _id 去重机制存储
# 部分关键词因 API 持续 504 错误只爬到了部分数据
PHASE_A_DONE = {
    'AI编程', 'Copilot', 'Cursor编辑器', 'vibe coding',
    '氛围编程', 'AI写代码', '代码审查 AI', 'AI结对编程',
    'AI生成代码', '不需要学编程', '调prompt就行',
    '程序员技能贬值', 'CRUD工程师末日', '胶水代码',
    '不需要懂底层'
}
# 检查已爬取的关键词（按 phase 分组）
def get_crawled_keywords(phase):
    """获取指定 phase 中已爬取的关键词列表"""
    pipeline = [
        {"$match": {"source": "github_issue", "phase": phase}},
        {"$group": {"_id": "$metadata.search_keyword"}}
    ]
    results = list(db.collection.aggregate(pipeline))
    return set(r['_id'] for r in results if r['_id'])

crawled_a = get_crawled_keywords('A') | PHASE_A_DONE
crawled_b = get_crawled_keywords('B')
logger.info(f"已爬取 Phase A 关键词: {crawled_a}")
logger.info(f"已爬取 Phase B 关键词: {crawled_b}")

# 覆盖 _execute 方法，增加超时和重试间隔
_original_execute = gh._execute
def _patched_execute(query, variables):
    max_retries = max(len(tokens) * 3, 6)
    for attempt in range(max_retries):
        try:
            resp = req_manager.post(
                gh.ENDPOINT,
                json={"query": query, "variables": variables},
                headers=gh._get_headers(),
                timeout=60  # 从30秒增加到60秒
            )
            if resp.status_code == 401:
                logger.error(f"[GitHub] Token {gh.token_idx} unauthorized (401), giving up.")
                return None
            if resp.status_code in (403, 429):
                reset_time = resp.headers.get("X-RateLimit-Reset")
                if reset_time:
                    wait = int(reset_time) - int(time.time()) + 5
                    wait = max(wait, 60)
                    wait = min(wait, 3600)
                else:
                    wait = min(60 * (attempt + 1), 3600)
                logger.warning(f"[GitHub] Rate limited (Token {gh.token_idx}), waiting {wait}s...")
                time.sleep(wait)
                gh._rotate_token()
                continue
            resp.raise_for_status()
            gh._check_rate_limit(resp.headers)
            data = resp.json()
            if "errors" in data:
                logger.error(f"[GitHub] GraphQL errors: {data['errors']}")
                return None
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"[GitHub] Request error (attempt {attempt+1}): {e}")
            wait_time = min(2 ** attempt * 2, 120)  # 最大等待120秒
            time.sleep(wait_time)
            if len(tokens) > 0 and attempt % len(tokens) == 0:
                gh._rotate_token()
    logger.error(f"[GitHub] All {max_retries} attempts failed for query.")
    return None

gh._execute = _patched_execute

# Phase A: 探索期
total_a = 0
logger.info(f">>> Phase A: {PHASE_A_START} ~ {PHASE_A_END}")
for kw in KEYWORDS:
    if kw in crawled_a:
        logger.info(f"[Skip] '{kw}' already crawled in Phase A")
        continue
    logger.info(f"[Crawl] '{kw}' Phase A...")
    time.sleep(random.uniform(3, 5))  # 关键词间延迟
    count = gh.crawl_search(kw, PHASE_A_START[:10], PHASE_A_END[:10], 'ISSUE', max_pages=MAX_PAGES)
    total_a += count
    if count == 0:
        logger.warning(f"[Retry] '{kw}' Phase A got 0, waiting 120s and retrying...")
        time.sleep(120)
        count = gh.crawl_search(kw, PHASE_A_START[:10], PHASE_A_END[:10], 'ISSUE', max_pages=MAX_PAGES)
        total_a += count

# Phase B: 范式震荡期
total_b = 0
logger.info(f">>> Phase B: {PHASE_B_START} ~ {PHASE_B_END}")
for kw in KEYWORDS:
    if kw in crawled_b:
        logger.info(f"[Skip] '{kw}' already crawled in Phase B")
        continue
    logger.info(f"[Crawl] '{kw}' Phase B...")
    time.sleep(random.uniform(3, 5))  # 关键词间延迟
    count = gh.crawl_search(kw, PHASE_B_START[:10], PHASE_B_END[:10], 'ISSUE', max_pages=MAX_PAGES)
    total_b += count
    if count == 0:
        logger.warning(f"[Retry] '{kw}' Phase B got 0, waiting 120s and retrying...")
        time.sleep(120)
        count = gh.crawl_search(kw, PHASE_B_START[:10], PHASE_B_END[:10], 'ISSUE', max_pages=MAX_PAGES)
        total_b += count

stats = db.get_stats()
logger.info("=" * 60)
logger.info(f"GitHub ZH crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
logger.info(f"DB stats: {stats}")
logger.info("=" * 60)

db.close()
