#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知乎数据爬虫
搜索中文关键词的问题和回答，存储到 MongoDB
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
        logging.FileHandler("crawler_zhihu.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 中文关键词（与 GitHub 爬虫一致）
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


class ZhihuCrawler:
    def __init__(self, db: DB):
        self.db = db
        self.session = requests.Session()
        # 知乎需要模拟浏览器
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.zhihu.com/",
        })

    def _request(self, url: str, params: Optional[Dict] = None,
                 max_retries: int = 5) -> Optional[Dict]:
        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    url, params=params, timeout=30
                )
                if resp.status_code == 403:
                    logger.warning(f"[ZH] 403 Forbidden, waiting 30s...")
                    time.sleep(30)
                    continue
                if resp.status_code == 429:
                    wait = min(60 * (attempt + 1), 300)
                    logger.warning(f"[ZH] Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    logger.warning(f"[ZH] HTTP {resp.status_code}, waiting 10s...")
                    time.sleep(10)
                    continue
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"[ZH] Error (attempt {attempt+1}): {e}")
                time.sleep(min(2 ** attempt * 5, 60))
            except json.JSONDecodeError as e:
                logger.error(f"[ZH] JSON decode error: {e}")
                time.sleep(5)
        return None

    def search_questions(self, keyword: str, offset: int = 0,
                         limit: int = 20) -> Optional[Dict]:
        """知乎搜索 API - 搜索问题"""
        url = "https://www.zhihu.com/api/v4/search_v3"
        params = {
            "t": "general",
            "q": keyword,
            "correction": 1,
            "offset": offset,
            "limit": limit,
            "show_all_topics": 0,
        }
        return self._request(url, params)

    def get_answers(self, question_id: str, offset: int = 0,
                    limit: int = 20) -> Optional[Dict]:
        """获取问题的回答"""
        url = f"https://www.zhihu.com/api/v4/questions/{question_id}/answers"
        params = {
            "include": "content,voteup_count,comment_count,created_time,updated_time",
            "offset": offset,
            "limit": limit,
            "sort_by": "created",
        }
        return self._request(url, params)

    def crawl_keyword(self, keyword: str, phase: str) -> int:
        """爬取一个关键词的知乎数据"""
        total = 0
        max_pages = 5  # 每个关键词最多搜5页

        logger.info(f"[ZH] Searching: kw={keyword}, phase={phase}")

        for page in range(max_pages):
            offset = page * 20
            data = self.search_questions(keyword, offset=offset)
            if not data:
                break

            items = data.get("data", [])
            if not items:
                break

            for item in items:
                obj = item.get("object", {})
                question = obj.get("question", {})
                
                # 提取问题信息
                q_id = question.get("id", "")
                q_title = question.get("title", "")
                q_url = question.get("url", "")
                q_created = question.get("created", 0)
                q_detail = question.get("detail", "")

                if not q_id:
                    continue

                # 判断时间是否在 phase 范围内
                created_dt = datetime.fromtimestamp(q_created, tz=timezone.utc)
                created_str = created_dt.strftime("%Y-%m-%d")

                if phase == "A":
                    if created_str > PHASE_A_END or created_str < PHASE_A_START:
                        continue
                elif phase == "B":
                    if created_str > PHASE_B_END or created_str < PHASE_B_START:
                        continue

                # 存储问题
                q_doc = {
                    "source": "zhihu_question",
                    "phase": phase,
                    "lang": "zh",
                    "url": f"https://www.zhihu.com/question/{q_id}",
                    "title": q_title,
                    "text": q_detail or "",
                    "created_at": created_str,
                    "author": question.get("author", {}).get("name", "") if question.get("author") else "",
                    "metadata": {
                        "question_id": q_id,
                        "search_keyword": keyword,
                        "answer_count": question.get("answer_count", 0),
                        "comment_count": question.get("comment_count", 0),
                        "follower_count": question.get("follower_count", 0),
                    }
                }
                self.db.insert(q_doc)
                total += 1

                # 获取前10个回答
                answers_data = self.get_answers(q_id, limit=10)
                if answers_data:
                    for ans in answers_data.get("data", []):
                        ans_created = ans.get("created_time", 0)
                        ans_dt = datetime.fromtimestamp(ans_created, tz=timezone.utc)
                        ans_str = ans_dt.strftime("%Y-%m-%d")

                        # 检查回答时间是否在 phase 范围内
                        if phase == "A":
                            if ans_str > PHASE_A_END or ans_str < PHASE_A_START:
                                continue
                        elif phase == "B":
                            if ans_str > PHASE_B_END or ans_str < PHASE_B_START:
                                continue

                        ans_doc = {
                            "source": "zhihu_answer",
                            "phase": phase,
                            "lang": "zh",
                            "url": f"https://www.zhihu.com/question/{q_id}/answer/{ans.get('id', '')}",
                            "title": "",
                            "text": ans.get("content", "") or "",
                            "created_at": ans_str,
                            "author": ans.get("author", {}).get("name", "") if ans.get("author") else "",
                            "metadata": {
                                "question_id": q_id,
                                "question_title": q_title,
                                "search_keyword": keyword,
                                "voteup_count": ans.get("voteup_count", 0),
                                "comment_count": ans.get("comment_count", 0),
                            }
                        }
                        self.db.insert(ans_doc)
                        total += 1

                time.sleep(random.uniform(2, 4))

            time.sleep(random.uniform(3, 6))

        logger.info(f"[ZH] Finished: {total} items for '{keyword}' phase={phase}")
        return total


def main():
    logger.info("=" * 60)
    logger.info("知乎数据爬虫")
    logger.info("=" * 60)

    db = DB(MONGO_URI, DB_NAME)
    crawler = ZhihuCrawler(db)

    total_a = 0
    logger.info(f">>> Phase A: {PHASE_A_START} ~ {PHASE_A_END}")
    for kw in KEYWORDS:
        logger.info(f"[Crawl] '{kw}' Phase A...")
        time.sleep(random.uniform(3, 6))
        count = crawler.crawl_keyword(kw, "A")
        total_a += count

    total_b = 0
    logger.info(f">>> Phase B: {PHASE_B_START} ~ {PHASE_B_END}")
    for kw in KEYWORDS:
        logger.info(f"[Crawl] '{kw}' Phase B...")
        time.sleep(random.uniform(3, 6))
        count = crawler.crawl_keyword(kw, "B")
        total_b += count

    logger.info("=" * 60)
    logger.info(f"知乎 crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
    logger.info("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
