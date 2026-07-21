#!/usr/bin/env python3
"""GitHub 全量采集（仅 Issue，扩展关键词和页数）"""
import os

if 'MONGO_URI' not in os.environ:
    os.environ['MONGO_URI'] = 'mongodb://localhost:27017/coding_labor'

from crawler import (
    DatabaseManager, GitHubCrawler, KEYWORDS_EN, logger,
    PHASE_A_START, PHASE_A_END, PHASE_B_START, PHASE_B_END
)

logger.info("=" * 60)
logger.info("GitHub Full Crawl (Issue Only)")
logger.info("=" * 60)

db = DatabaseManager(os.environ['MONGO_URI'], "coding_labor")

tokens = [t for t in [
    os.environ.get('GITHUB_TOKEN_1', ''),
    os.environ.get('GITHUB_TOKEN_2', ''),
    os.environ.get('GITHUB_TOKEN_3', ''),
] if t]

gh = GitHubCrawler(tokens, db)

# 扩展配置
KEYWORDS = KEYWORDS_EN  # 全部 20 个关键词
MAX_PAGES = 10          # 每关键词采 10 页（每页 50 条，最多 500 条/关键词）

# Phase A: 探索期
total_a = 0
logger.info(f">>> Phase A: {PHASE_A_START} ~ {PHASE_A_END}")
for kw in KEYWORDS:
    total_a += gh.crawl_search(kw, PHASE_A_START[:10], PHASE_A_END[:10], 'ISSUE', max_pages=MAX_PAGES)

# Phase B: 范式震荡期
total_b = 0
logger.info(f">>> Phase B: {PHASE_B_START} ~ {PHASE_B_END}")
for kw in KEYWORDS:
    total_b += gh.crawl_search(kw, PHASE_B_START[:10], PHASE_B_END[:10], 'ISSUE', max_pages=MAX_PAGES)

stats = db.get_stats()
logger.info("=" * 60)
logger.info(f"GitHub full crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
logger.info(f"DB stats: {stats}")
logger.info("=" * 60)

db.close()
