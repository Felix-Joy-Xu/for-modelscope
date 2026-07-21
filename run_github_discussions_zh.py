#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Discussions 中文数据爬取
用 GraphQL API 搜索中文关键词的 Discussions
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
        logging.FileHandler("crawler_discussions_zh.log", encoding='utf-8'),
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

GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

SEARCH_QUERY = """
query($query: String!, $cursor: String) {
  search(query: $query, type: DISCUSSION, first: 100, after: $cursor) {
    discussionCount
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on Discussion {
        title
        url
        createdAt
        body
        author { login }
        repository { nameWithOwner }
        category { name }
      }
    }
  }
}
"""


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
            "Authorization": f"Bearer {self.tokens[self.token_idx]}",
            "Content-Type": "application/json",
            "User-Agent": "AcademicResearch/1.0"
        }

    def _rotate_token(self):
        old = self.token_idx
        self.token_idx = (self.token_idx + 1) % len(self.tokens)
        logger.warning(f"[GQL] Token rotated: {old} -> {self.token_idx}")

    def _execute(self, query: str, variables: Dict) -> Optional[Dict]:
        max_retries = 10
        for attempt in range(max_retries):
            try:
                resp = self.session.post(
                    GRAPHQL_ENDPOINT,
                    json={"query": query, "variables": variables},
                    headers=self._get_headers(),
                    timeout=120
                )
                if resp.status_code == 401:
                    logger.error(f"[GQL] Token {self.token_idx} unauthorized")
                    return None
                if resp.status_code in (403, 429):
                    reset_time = resp.headers.get("X-RateLimit-Reset")
                    if reset_time:
                        wait = int(reset_time) - int(time.time()) + 5
                        wait = max(wait, 60)
                        wait = min(wait, 3600)
                    else:
                        wait = min(120 * (attempt + 1), 3600)
                    logger.warning(f"[GQL] Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    self._rotate_token()
                    continue
                if resp.status_code in (502, 503, 504):
                    wait = min(30 * (attempt + 1), 300)
                    logger.warning(f"[GQL] Server error {resp.status_code}, waiting {wait}s...")
                    time.sleep(wait)
                    self._rotate_token()
                    continue
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data:
                    logger.error(f"[GQL] GraphQL errors: {data['errors']}")
                    return None
                return data
            except requests.exceptions.RequestException as e:
                logger.error(f"[GQL] Error (attempt {attempt+1}): {e}")
                wait_time = min(30 * (attempt + 1), 300)
                time.sleep(wait_time)
                self._rotate_token()
        logger.error(f"[GQL] All {max_retries} attempts failed")
        return None

    def crawl_keyword(self, keyword: str, start_date: str, end_date: str,
                      phase: str) -> int:
        gql_query = f'{keyword} created:{start_date}..{end_date}'
        variables = {"query": gql_query, "cursor": None}

        total = 0
        page = 0
        max_pages = 10

        logger.info(f"[GQL] Starting: kw={keyword}, phase={phase}")

        while page < max_pages:
            data = self._execute(SEARCH_QUERY, variables)
            if not data:
                break

            search = data.get("data", {}).get("search", {})
            nodes = search.get("nodes", [])
            if not nodes:
                break

            for node in nodes:
                discussion_doc = {
                    "source": "github_discussion",
                    "phase": phase,
                    "lang": "zh",
                    "url": node.get("url", ""),
                    "title": node.get("title", ""),
                    "text": node.get("body", "") or "",
                    "created_at": node.get("createdAt", ""),
                    "author": node.get("author", {}).get("login") if node.get("author") else None,
                    "metadata": {
                        "repo": node.get("repository", {}).get("nameWithOwner", ""),
                        "search_keyword": keyword,
                        "comments_count": node.get("comments", {}).get("totalCount", 0),
                        "category": node.get("category", {}).get("name", "") if node.get("category") else ""
                    }
                }
                self.db.insert(discussion_doc)
                total += 1

                comments = node.get("comments", {}).get("nodes", [])
                for c in comments:
                    comment_doc = {
                        "source": "github_comment",
                        "phase": phase,
                        "lang": "zh",
                        "url": c.get("url", node.get("url", "")),
                        "title": "",
                        "text": c.get("body", "") or "",
                        "created_at": c.get("createdAt", ""),
                        "author": c.get("author", {}).get("login") if c.get("author") else None,
                        "metadata": {
                            "repo": "",
                            "parent_type": "discussion",
                            "parent_id": node.get("url", ""),
                            "search_keyword": keyword
                        }
                    }
                    self.db.insert(comment_doc)

            page += 1
            logger.info(f"[GQL] Page {page}: {len(nodes)} discussions, total={total}")

            page_info = search.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            variables["cursor"] = page_info.get("endCursor")

            time.sleep(random.uniform(3, 6))

        logger.info(f"[GQL] Finished: {total} discussions for '{keyword}' phase={phase}")
        return total


def main():
    logger.info("=" * 60)
    logger.info("GitHub Discussions 中文数据爬取 (GraphQL)")
    logger.info("=" * 60)

    db = DB(MONGO_URI, DB_NAME)
    crawler = GitHubDiscussionCrawler(TOKENS, db)

    total_a = 0
    logger.info(f">>> Phase A: {PHASE_A_START} ~ {PHASE_A_END}")
    for kw in KEYWORDS_ZH:
        logger.info(f"[Crawl] '{kw}' Phase A...")
        time.sleep(random.uniform(3, 6))
        count = crawler.crawl_keyword(kw, PHASE_A_START, PHASE_A_END, "A")
        total_a += count

    total_b = 0
    logger.info(f">>> Phase B: {PHASE_B_START} ~ {PHASE_B_END}")
    for kw in KEYWORDS_ZH:
        logger.info(f"[Crawl] '{kw}' Phase B...")
        time.sleep(random.uniform(3, 6))
        count = crawler.crawl_keyword(kw, PHASE_B_START, PHASE_B_END, "B")
        total_b += count

    logger.info("=" * 60)
    logger.info(f"中文 Discussions crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
    logger.info("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
