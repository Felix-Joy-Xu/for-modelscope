#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
掘金数据爬虫
搜索中文关键词的文章和评论，存储到 MongoDB
"""
import os
import sys
import time
import random
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List

import requests
from pymongo import MongoClient, errors as mongo_errors

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/coding_labor")
DB_NAME = os.getenv("DB_NAME", "coding_labor")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("crawler_juejin.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 中文关键词
KEYWORDS = [
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


class JuejinCrawler:
    def __init__(self, db: DB):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        })

    def _request(self, url: str, json_data: Dict,
                 max_retries: int = 5) -> Optional[Dict]:
        for attempt in range(max_retries):
            try:
                resp = self.session.post(url, json=json_data, timeout=30)
                if resp.status_code == 429:
                    wait = min(60 * (attempt + 1), 300)
                    logger.warning(f"[JJ] Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if data.get("err_no") != 0:
                    logger.warning(f"[JJ] API error: {data.get('err_msg', '')}")
                    return None
                return data
            except requests.exceptions.RequestException as e:
                logger.error(f"[JJ] Error (attempt {attempt+1}): {e}")
                time.sleep(min(2 ** attempt * 5, 60))
        return None

    def search_articles(self, keyword: str, cursor: str = "0",
                        limit: int = 50) -> Optional[Dict]:
        """搜索掘金文章"""
        url = "https://api.juejin.cn/search_api/v1/search"
        data = {
            "key_word": keyword,
            "cursor": cursor,
            "limit": limit,
            "sort": 0  # 0=综合, 1=最新
        }
        return self._request(url, data)

    def get_article_detail(self, article_id: str) -> Optional[Dict]:
        """获取文章详情（含正文）"""
        url = "https://api.juejin.cn/content_api/v1/article/detail"
        data = {"article_id": article_id}
        return self._request(url, data)

    def get_comments(self, article_id: str, cursor: str = "0",
                     limit: int = 20) -> Optional[Dict]:
        """获取文章评论"""
        url = "https://api.juejin.cn/interact_api/v1/comment/list"
        data = {
            "item_id": article_id,
            "item_type": 2,
            "cursor": cursor,
            "limit": limit,
        }
        return self._request(url, data)

    def crawl_keyword(self, keyword: str, phase: str) -> int:
        """爬取一个关键词的掘金数据"""
        total = 0
        cursor = "0"
        max_pages = 5

        logger.info(f"[JJ] Searching: kw={keyword}, phase={phase}")

        for page in range(max_pages):
            data = self.search_articles(keyword, cursor=cursor)
            if not data:
                break

            items = data.get("data", [])
            if not items:
                break

            has_more = data.get("has_more", False)

            for item in items:
                model = item.get("result_model", {})
                if not model:
                    continue

                # 文章信息在 article_info 中
                article_info = model.get("article_info", {})
                if not article_info:
                    continue

                article_id = article_info.get("article_id", "")
                title = article_info.get("title", "")
                # 掘金时间戳是毫秒
                created_ts = article_info.get("ctime", "0")
                if created_ts:
                    created_dt = datetime.fromtimestamp(int(created_ts), tz=timezone.utc)
                    created_str = created_dt.strftime("%Y-%m-%d")
                else:
                    created_str = ""

                # 判断时间是否在 phase 范围内
                if phase == "A":
                    if created_str > PHASE_A_END or created_str < PHASE_A_START:
                        continue
                elif phase == "B":
                    if created_str > PHASE_B_END or created_str < PHASE_B_START:
                        continue

                # 获取文章详情（含正文）
                detail = self.get_article_detail(article_id)
                content = ""
                if detail:
                    detail_data = detail.get("data", {})
                    article_detail = detail_data.get("article_info", {})
                    content = article_detail.get("content", "") or ""

                # 获取作者信息
                author_info = model.get("author_user_info", {}) or \
                              article_info.get("user_info", {})

                # 存储文章
                article_doc = {
                    "source": "juejin_article",
                    "phase": phase,
                    "lang": "zh",
                    "url": f"https://juejin.cn/post/{article_id}",
                    "title": title,
                    "text": content,
                    "created_at": created_str,
                    "author": author_info.get("user_name", "") if author_info else "",
                    "metadata": {
                        "article_id": article_id,
                        "search_keyword": keyword,
                        "category": model.get("category", {}).get("category_name", ""),
                        "tags": [t.get("tag_name", "") for t in model.get("tag_list", [])],
                        "view_count": article_info.get("view_count", 0),
                        "digg_count": article_info.get("digg_count", 0),
                        "comment_count": article_info.get("comment_count", 0),
                    }
                }
                self.db.insert(article_doc)
                total += 1

                # 获取评论
                comments_data = self.get_comments(article_id)
                if comments_data:
                    for comment in comments_data.get("data", []):
                        comment_info = comment.get("comment_info", {}) or comment
                        comment_ts = comment_info.get("ctime", 0)
                        if comment_ts:
                            comment_dt = datetime.fromtimestamp(comment_ts, tz=timezone.utc)
                            comment_str = comment_dt.strftime("%Y-%m-%d")
                        else:
                            comment_str = ""

                        comment_doc = {
                            "source": "juejin_comment",
                            "phase": phase,
                            "lang": "zh",
                            "url": f"https://juejin.cn/post/{article_id}#comment-{comment_info.get('comment_id', '')}",
                            "title": "",
                            "text": comment_info.get("content", "") or "",
                            "created_at": comment_str,
                            "author": comment_info.get("user_name", "") or "",
                            "metadata": {
                                "article_id": article_id,
                                "article_title": title,
                                "search_keyword": keyword,
                                "digg_count": comment_info.get("digg_count", 0),
                            }
                        }
                        self.db.insert(comment_doc)
                        total += 1

                time.sleep(random.uniform(1, 2))

            if not has_more:
                break

            cursor = str(int(cursor) + 50)
            time.sleep(random.uniform(2, 4))

        logger.info(f"[JJ] Finished: {total} items for '{keyword}' phase={phase}")
        return total


def main():
    logger.info("=" * 60)
    logger.info("掘金数据爬虫")
    logger.info("=" * 60)

    db = DB(MONGO_URI, DB_NAME)
    crawler = JuejinCrawler(db)

    total_a = 0
    logger.info(f">>> Phase A: {PHASE_A_START} ~ {PHASE_A_END}")
    for kw in KEYWORDS:
        logger.info(f"[Crawl] '{kw}' Phase A...")
        time.sleep(random.uniform(2, 4))
        count = crawler.crawl_keyword(kw, "A")
        total_a += count

    total_b = 0
    logger.info(f">>> Phase B: {PHASE_B_START} ~ {PHASE_B_END}")
    for kw in KEYWORDS:
        logger.info(f"[Crawl] '{kw}' Phase B...")
        time.sleep(random.uniform(2, 4))
        count = crawler.crawl_keyword(kw, "B")
        total_b += count

    logger.info("=" * 60)
    logger.info(f"掘金 crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
    logger.info("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
