#!/usr/bin/env python3
"""只运行 GitHub Issue 爬虫（不需要 read:discussion 权限）"""
import os
import mongomock
import pymongo

pymongo.MongoClient = mongomock.MongoClient

if 'MONGO_URI' not in os.environ:
    os.environ['MONGO_URI'] = 'mongodb://localhost:27017/coding_labor'

tokens = [t for t in [
    os.environ.get('GITHUB_TOKEN_1', ''),
    os.environ.get('GITHUB_TOKEN_2', ''),
    os.environ.get('GITHUB_TOKEN_3', ''),
] if t]

from crawler import DatabaseManager, GitHubCrawler, logger

logger.info("=" * 60)
logger.info("GitHub Issue-Only Test Run")
logger.info("=" * 60)

db = DatabaseManager(os.environ['MONGO_URI'], "coding_labor")
gh = GitHubCrawler(tokens, db)

# 只跑 Issue，1 个关键词，最多 2 页
total = gh.crawl_search('copilot', '2024-03-01', '2024-03-31', 'ISSUE', max_pages=2)
logger.info(f"GitHub Issue-only total: {total}")

db.close()
