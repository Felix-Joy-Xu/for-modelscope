#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 中文关键词爬取 - REST API 版
使用 GitHub REST Search API 替代 GraphQL，更稳定，不易 504
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

# ===== 配置 =====
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/coding_labor")
DB_NAME = os.getenv("DB_NAME", "coding_labor")
TOKENS = [t for t in [
    os.getenv("GITHUB_TOKEN_1", ""),
    os.getenv("GITHUB_TOKEN_2", ""),
    os.getenv("GITHUB_TOKEN_3", ""),
] if t]

# 日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("crawler_zh_rest.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 中文关键词（与 crawler.py 保持一致）
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

# 已完成的 Phase A 关键词（跳过）
PHASE_A_DONE = {
    'AI编程', 'Copilot', 'Cursor编辑器', 'vibe coding',
    '氛围编程', 'AI写代码', '代码审查 AI', 'AI结对编程',
    'AI生成代码', '不需要学编程', '调prompt就行',
    '程序员技能贬值', 'CRUD工程师末日', '胶水代码',
    '不需要懂底层'
}

# ===== MongoDB =====
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

    def get_crawled_keywords(self, phase: str) -> set:
        """获取指定 phase 中已爬取的关键词"""
        pipeline = [
            {"$match": {"source": "github_issue", "phase": phase}},
            {"$group": {"_id": "$metadata.search_keyword"}}
        ]
        results = list(self.collection.aggregate(pipeline))
        return set(r['_id'] for r in results if r['_id'])

    def get_stats(self) -> Dict:
        pipeline = [
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return {item["_id"]: item["count"] for item in self.collection.aggregate(pipeline)}

    def close(self):
        self.client.close()


# ===== GitHub REST API Crawler =====
class GitHubRESTCrawler:
    """
    使用 GitHub REST Search API 爬取 Issues
    REST API 比 GraphQL 更稳定，不易出现 504
    """
    SEARCH_URL = "https://api.github.com/search/issues"

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

    def _request(self, url: str, params: Dict) -> Optional[Dict]:
        """带重试的 GET 请求"""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30
                )
                if resp.status_code == 401:
                    logger.error(f"[REST] Token {self.token_idx} unauthorized")
                    return None
                if resp.status_code == 403:
                    logger.warning(f"[REST] Rate limited (Token {self.token_idx}), waiting 60s...")
                    time.sleep(60)
                    self._rotate_token()
                    continue
                if resp.status_code == 422:
                    logger.error(f"[REST] Unprocessable: {resp.text}")
                    return None
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"[REST] Error (attempt {attempt+1}): {e}")
                wait = min(2 ** attempt * 5, 60)
                time.sleep(wait)
                self._rotate_token()
        logger.error(f"[REST] All {max_retries} attempts failed")
        return None

    def crawl_keyword(self, keyword: str, start_date: str, end_date: str, phase: str) -> int:
        """
        爬取单个关键词的 Issues
        使用 REST API 的 search/issues 端点
        """
        # 构建查询: keyword + 时间范围 + 只搜 issue
        q = f'"{keyword}" type:issue created:{start_date}..{end_date}'
        params = {
            "q": q,
            "sort": "created",
            "order": "desc",
            "per_page": 100,  # REST API 每页最多 100 条
        }

        page = 1
        total = 0
        max_pages = 10  # 最多 10 页 = 1000 条

        logger.info(f"[REST] Starting: kw={keyword}, phase={phase}")

        while page <= max_pages:
            params["page"] = page
            data = self._request(self.SEARCH_URL, params)
            if not data:
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                # 保存 Issue
                issue_doc = {
                    "source": "github_issue",
                    "phase": phase,
                    "lang": "zh",
                    "url": item.get("html_url", ""),
                    "title": item.get("title", ""),
                    "text": item.get("body", "") or "",
                    "created_at": item.get("created_at", ""),
                    "author": item.get("user", {}).get("login") if item.get("user") else None,
                    "metadata": {
                        "repo": item.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                        "state": item.get("state", "UNKNOWN"),
                        "node_id": item.get("node_id", ""),
                        "search_keyword": keyword,
                        "comments_count": item.get("comments", 0)
                    }
                }
                self.db.insert(issue_doc)
                total += 1

                # 如果有评论，也爬取评论
                comments_url = item.get("comments_url", "")
                if comments_url and item.get("comments", 0) > 0:
                    self._crawl_comments(comments_url, item.get("html_url", ""),
                                         item.get("node_id", ""), phase, keyword)

            logger.info(f"[REST] Page {page}: {len(items)} items, total={total}")
            page += 1

            # 检查是否还有更多页
            if len(items) < 100:
                break

            # 礼貌延迟
            time.sleep(random.uniform(2, 4))

        logger.info(f"[REST] Finished: {total} issues for '{keyword}' phase={phase}")
        return total

    def _crawl_comments(self, comments_url: str, issue_url: str,
                        issue_node_id: str, phase: str, keyword: str):
        """爬取 Issue 的评论"""
        page = 1
        total = 0
        max_pages = 5  # 最多 5 页评论

        while page <= max_pages:
            url = f"{comments_url}?page={page}&per_page=100"
            try:
                resp = self.session.get(url, headers=self._get_headers(), timeout=30)
                if resp.status_code != 200:
                    break
                comments = resp.json()
                if not comments:
                    break

                for c in comments:
                    comment_doc = {
                        "source": "github_comment",
                        "phase": phase,
                        "lang": "zh",
                        "url": c.get("html_url", issue_url),
                        "title": "",
                        "text": c.get("body", "") or "",
                        "created_at": c.get("created_at", ""),
                        "author": c.get("user", {}).get("login") if c.get("user") else None,
                        "metadata": {
                            "repo": "",
                            "parent_type": "issue",
                            "parent_id": issue_node_id,
                            "search_keyword": keyword
                        }
                    }
                    self.db.insert(comment_doc)
                    total += 1

                page += 1
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"[REST] Comment crawl error: {e}")
                break


# ===== Main =====
def main():
    logger.info("=" * 60)
    logger.info("GitHub ZH Crawl (REST API) - 更稳定版")
    logger.info("=" * 60)

    db = DB(MONGO_URI, DB_NAME)
    crawler = GitHubRESTCrawler(TOKENS, db)

    # 获取已爬取的关键词
    crawled_a = db.get_crawled_keywords('A') | PHASE_A_DONE
    crawled_b = db.get_crawled_keywords('B')
    logger.info(f"Phase A 已爬取: {crawled_a}")
    logger.info(f"Phase B 已爬取: {crawled_b}")

    # Phase A
    total_a = 0
    logger.info(f">>> Phase A: {PHASE_A_START} ~ {PHASE_A_END}")
    for kw in KEYWORDS_ZH:
        if kw in crawled_a:
            logger.info(f"[Skip] '{kw}' Phase A already done")
            continue
        logger.info(f"[Crawl] '{kw}' Phase A...")
        time.sleep(random.uniform(2, 4))
        count = crawler.crawl_keyword(kw, PHASE_A_START, PHASE_A_END, "A")
        total_a += count
        if count == 0:
            logger.warning(f"[Retry] '{kw}' got 0, waiting 60s...")
            time.sleep(60)
            count = crawler.crawl_keyword(kw, PHASE_A_START, PHASE_A_END, "A")
            total_a += count

    # Phase B
    total_b = 0
    logger.info(f">>> Phase B: {PHASE_B_START} ~ {PHASE_B_END}")
    for kw in KEYWORDS_ZH:
        if kw in crawled_b:
            logger.info(f"[Skip] '{kw}' Phase B already done")
            continue
        logger.info(f"[Crawl] '{kw}' Phase B...")
        time.sleep(random.uniform(2, 4))
        count = crawler.crawl_keyword(kw, PHASE_B_START, PHASE_B_END, "B")
        total_b += count
        if count == 0:
            logger.warning(f"[Retry] '{kw}' got 0, waiting 60s...")
            time.sleep(60)
            count = crawler.crawl_keyword(kw, PHASE_B_START, PHASE_B_END, "B")
            total_b += count

    stats = db.get_stats()
    logger.info("=" * 60)
    logger.info(f"ZH crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
    logger.info(f"DB stats: {stats}")
    logger.info("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
