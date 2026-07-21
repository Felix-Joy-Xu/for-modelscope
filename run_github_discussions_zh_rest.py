#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Discussions 中文数据爬取 - REST API 版
用 search/issues REST API 搜索中文关键词的 Discussions
"""
import os
import sys
import time
import random
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List

import requests
from pymongo import MongoClient, errors as mongo_errors

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/coding_labor")
DB_NAME = os.getenv("DB_NAME", "coding_labor")
TOKENS = [t for t in [
    os.getenv("GITHUB_TOKEN_1", ""),
    os.getenv("GITHUB_TOKEN_2", ""),
    os.getenv("GITHUB_TOKEN_3", ""),
] if t]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("crawler_discussions_zh_rest.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 中文关键词
KEYWORDS_ZH = [
    'AI编程', 'Copilot', 'Cursor编辑器', 'vibe coding', '氛围编程', 'AI写代码',
    '代码审查 AI', 'AI结对编程', 'AI生成代码',
    '不需要学编程', '调prompt就行', '程序员技能贬值', 'CRUD工程师末日',
    '胶水代码', '不需要懂底层', '编程门槛降低',
    '初级程序员失业', '外包程序员 AI', '架构师 AI', '程序员两极分化',
    '中级程序员消失', '全栈工程师 AI',
    '程序员裁员', 'AI裁员', '产出增加工资不变', '老板买AI裁员', '剩余价值',
    '程序员被剥削', '效率提升归谁',
    '程序员35岁危机', '程序员转行', '考公 程序员', '程序员失业',
    '程序员焦虑', '技术人退路', '被优化', '互联网寒冬',
    'AI控制程序员', '程序员自主性', 'AI替代决策', '代码工人'
]

PHASE_A_START = "2022-11-30"
PHASE_A_END = "2024-02-29"
PHASE_B_START = "2024-03-01"
PHASE_B_END = "2026-05-08"


class DB:
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name]
        self.collection = self.db["raw_posts"]
        logger.info(f"[DB] Connected to {db_name}")

    @staticmethod
    def generate_id(doc: Dict) -> str:
        url = doc.get("url", "")
        text_prefix = doc.get("text", "")[:100]
        return hashlib.sha256(f"{url}_{text_prefix}".encode()).hexdigest()

    def insert(self, doc: Dict) -> bool:
        try:
            doc_id = self.generate_id(doc)
            doc["_id"] = doc_id
            doc["crawled_at"] = datetime.now(timezone.utc).isoformat()
            doc["version"] = "1.0"
            self.collection.insert_one(doc)
            return True
        except mongo_errors.DuplicateKeyError:
            return True
        except Exception as e:
            logger.error(f"[DB] Insert error: {e}")
            return False

    def close(self):
        self.client.close()


class GitHubDiscussionCrawler:
    def __init__(self, tokens: List[str], db: DB):
        self.tokens = tokens
        self.token_idx = 0
        self.db = db
        self.session = requests.Session()

    def _get_headers(self) -> Dict:
        return {
            "Authorization": f"token {self.tokens[self.token_idx]}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AcademicResearch/1.0"
        }

    def _rotate_token(self):
        old = self.token_idx
        self.token_idx = (self.token_idx + 1) % len(self.tokens)
        logger.warning(f"[REST] Token rotated: {old} -> {self.token_idx}")

    def _request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        max_retries = 10
        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=60
                )
                if resp.status_code == 401:
                    logger.error(f"[REST] Token {self.token_idx} unauthorized")
                    return None
                if resp.status_code == 403:
                    logger.warning(f"[REST] Rate limited, waiting 60s...")
                    time.sleep(60)
                    self._rotate_token()
                    continue
                if resp.status_code in (502, 503, 504):
                    wait = min(30 * (attempt + 1), 120)
                    logger.warning(f"[REST] Server error {resp.status_code}, waiting {wait}s...")
                    time.sleep(wait)
                    self._rotate_token()
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"[REST] Error (attempt {attempt+1}): {e}")
                wait = min(2 ** attempt * 5, 60)
                time.sleep(wait)
                self._rotate_token()
        return None

    def crawl_keyword(self, keyword: str, start_date: str, end_date: str,
                      phase: str) -> int:
        """
        用 search/issues REST API 搜索 Discussions
        GitHub 的 search/issues 可以搜索到 Discussions
        """
        total = 0
        page = 1
        max_pages = 10

        logger.info(f"[REST] Starting: kw={keyword}, phase={phase}")

        while page <= max_pages:
            url = "https://api.github.com/search/issues"
            params = {
                "q": f'{keyword} created:{start_date}..{end_date} type:discussion',
                "per_page": 100,
                "page": page,
                "sort": "created",
                "order": "desc"
            }

            data = self._request(url, params)
            if not data:
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                discussion_doc = {
                    "source": "github_discussion",
                    "phase": phase,
                    "lang": "zh",
                    "url": item.get("html_url", ""),
                    "title": item.get("title", ""),
                    "text": item.get("body", "") or "",
                    "created_at": item.get("created_at", ""),
                    "author": item.get("user", {}).get("login") if item.get("user") else None,
                    "metadata": {
                        "repo": item.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                        "search_keyword": keyword,
                        "comments_count": item.get("comments", 0),
                        "category": item.get("labels", [{}])[0].get("name", "") if item.get("labels") else ""
                    }
                }
                self.db.insert(discussion_doc)
                total += 1

            logger.info(f"[REST] Page {page}: {len(items)} discussions, total={total}")
            page += 1
            time.sleep(random.uniform(2, 4))

        logger.info(f"[REST] Finished: {total} discussions for '{keyword}' phase={phase}")
        return total


def main():
    logger.info("=" * 60)
    logger.info("GitHub Discussions 中文数据爬取 (REST API)")
    logger.info("=" * 60)

    db = DB(MONGO_URI, DB_NAME)
    crawler = GitHubDiscussionCrawler(TOKENS, db)

    total_a = 0
    logger.info(f">>> Phase A: {PHASE_A_START} ~ {PHASE_A_END}")
    for kw in KEYWORDS_ZH:
        logger.info(f"[Crawl] '{kw}' Phase A...")
        time.sleep(random.uniform(2, 4))
        count = crawler.crawl_keyword(kw, PHASE_A_START, PHASE_A_END, "A")
        total_a += count

    total_b = 0
    logger.info(f">>> Phase B: {PHASE_B_START} ~ {PHASE_B_END}")
    for kw in KEYWORDS_ZH:
        logger.info(f"[Crawl] '{kw}' Phase B...")
        time.sleep(random.uniform(2, 4))
        count = crawler.crawl_keyword(kw, PHASE_B_START, PHASE_B_END, "B")
        total_b += count

    logger.info("=" * 60)
    logger.info(f"中文 Discussions crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
    logger.info("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
