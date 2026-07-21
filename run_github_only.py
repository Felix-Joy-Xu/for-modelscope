#!/usr/bin/env python3
"""只运行 GitHub 爬虫，用于测试修复后的错误处理和 Token 轮换逻辑"""
import os
import mongomock
import pymongo

# Mock MongoDB
pymongo.MongoClient = mongomock.MongoClient

# 优先使用外部传入的环境变量
if 'MONGO_URI' not in os.environ:
    os.environ['MONGO_URI'] = 'mongodb://localhost:27017/test_crawler'

# 收集所有非空 GitHub Token
tokens = [t for t in [
    os.environ.get('GITHUB_TOKEN_1', ''),
    os.environ.get('GITHUB_TOKEN_2', ''),
    os.environ.get('GITHUB_TOKEN_3', ''),
] if t]

from crawler import DatabaseManager, GitHubCrawler, logger

# 初始化
logger.info("=" * 60)
logger.info("GitHub-Only Test Run")
logger.info("=" * 60)

db = DatabaseManager(os.environ['MONGO_URI'], "coding_labor")
gh = GitHubCrawler(tokens, db)

# 只跑 1 个关键词、1 个类型、最多 2 页，快速验证
total = gh.crawl_search('copilot', '2024-03-01', '2024-03-31', 'DISCUSSION', max_pages=2)
logger.info(f"GitHub-only total: {total}")

db.close()
