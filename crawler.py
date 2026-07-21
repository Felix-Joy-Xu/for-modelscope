#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Political Economy of AI Coding Labor - Data Acquisition Framework
================================================================
理论视角: 政治经济学 + 劳动经济学
采集目标: 程序员社区中关于AI编程工具对劳动过程、技能结构、
         剩余价值分配与不稳定性就业的话语

时间窗口:
  Phase A (探索期): 2022-11-30 ~ 2024-02-29
  Phase B (范式震荡期): 2024-03-01 ~ 2026-05-08

数据源:
  EN: GitHub Discussions/Issues, Hacker News, Reddit
  ZH: V2EX, 掘金 (Juejin)

作者: Researcher
日期: 2026-05-08
"""

import os
import sys
import time
import hashlib
import random
import logging
import signal
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient, errors as mongo_errors
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================================
# 1. 配置层 (CONFIGURATION)
# ============================================================================

# --- MongoDB Atlas (数据湖) ---
# 建议: 使用 MongoDB Atlas 免费层 (512MB-5GB)
# 连接字符串格式: mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
MONGO_URI = os.getenv("MONGO_URI", "YOUR_MONGO_URI_HERE")
DB_NAME = os.getenv("DB_NAME", "coding_labor")
RAW_COLLECTION = "raw_posts"

# --- GitHub Personal Access Tokens (多Token轮换池) ---
# 申请方式: GitHub Settings -> Developer settings -> Personal access tokens -> Tokens (classic)
# Scope: 至少勾选 `repo` 和 `read:discussion`
# 建议准备 5-10 个Token，避免单Token触发 rate limit (5000 points/hour)
GITHUB_TOKENS = [
    os.getenv("GITHUB_TOKEN_1", ""),
    os.getenv("GITHUB_TOKEN_2", ""),
    os.getenv("GITHUB_TOKEN_3", ""),
]
# 过滤掉未配置的占位符
GITHUB_TOKENS = [t for t in GITHUB_TOKENS if t and not t.startswith("YOUR_")]

# --- Reddit API (PRAW) ---
# 申请方式: https://www.reddit.com/prefs/apps -> create app -> script
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "AcademicResearch/1.0 by Researcher")

# --- 掘金 (Juejin) 抓包参数 ---
# 由于掘金API需要动态签名，建议先用浏览器抓包获取以下参数:
# 1. 打开 https://juejin.cn/search?query=AI编程 并打开F12 Network
# 2. 找到 search_api/v1/search 请求，复制 aid, uuid, signature, _signature
# 3. 这些参数有有效期，建议每次采集前更新
JUEJIN_AID = os.getenv("JUEJIN_AID", "")          # 如: "2608"
JUEJIN_UUID = os.getenv("JUEJIN_UUID", "")        # 如: "7290399990000000000"
JUEJIN_SIGNATURE = os.getenv("JUEJIN_SIGNATURE", "")  # 从请求头或Cookie中提取

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("crawler.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- 时间窗口定义 ---
PHASE_A_START = "2022-11-30T00:00:00Z"
PHASE_A_END = "2024-02-29T23:59:59Z"
PHASE_B_START = "2024-03-01T00:00:00Z"
PHASE_B_END = "2026-05-08T23:59:59Z"

# Unix timestamp 版本 (用于HN)
TS_PHASE_A_START = 1669766400   # 2022-11-30
TS_PHASE_A_END = 1709251199     # 2024-02-29
TS_PHASE_B_START = 1709251200   # 2024-03-01
TS_PHASE_B_END = 1778284799     # 2026-05-08 23:59:59 UTC

# ============================================================================
# 2. 理论驱动的关键词矩阵 (THEORY-DRIVEN KEYWORDS)
# ============================================================================
# 关键词选择基于政治经济学核心概念:
# 劳动过程控制、去技能化、技能极化、剩余价值分配、劳动力商品化、不稳定就业

KEYWORDS_EN = [
    # 技术范式与劳动过程
    '"vibe coding"', '"ai coding"', 'copilot workflow', 'cursor editor workflow',
    '"code review" copilot', '"pair programming" ai', 'ai generated code maintenance',
    # 去技能化话语
    '"deskilling" programming', '"no need to learn" coding', '"prompt engineering" only',
    'junior developer obsolete', '"glue code" engineer',
    # 技能极化与劳动力市场
    '"programmer jobs" ai', '"replace programmers"', '"junior roles" dead',
    'ai layoffs tech', '"hiring freeze" software', 'entry level software 2024',
    # 剩余价值与剥削感知
    '"productivity gains" salary', '"10x engineer" ai', 'copilot fired employee',
    '"wage stagnation" tech', 'ai productivity who benefits',
    # 不稳定就业
    '"job insecurity" programmer', '"career change" tech', 'tech layoffs 2024 2025',
    '"imposter syndrome" ai', '"burnout" ai tools'
]

KEYWORDS_ZH = [
    # 技术范式
    'AI编程', 'Copilot', 'Cursor编辑器', 'vibe coding', '氛围编程', 'AI写代码',
    '代码审查 AI', 'AI结对编程', 'AI生成代码',
    # 去技能化
    '不需要学编程', '调prompt就行', '程序员技能贬值', 'CRUD工程师末日',
    '胶水代码', '不需要懂底层', '编程门槛降低',
    # 技能极化
    '初级程序员失业', '外包程序员 AI', '架构师 AI', '程序员两极分化',
    '中级程序员消失', '全栈工程师 AI',
    # 剩余价值
    '程序员裁员', 'AI裁员', '产出增加工资不变', '老板买AI裁员', '剩余价值',
    '程序员被剥削', '效率提升归谁',
    # 不稳定就业
    '程序员35岁危机', '程序员转行', '考公 程序员', '程序员失业',
    '程序员焦虑', '技术人退路', '被优化', '互联网寒冬',
    # 劳动过程控制
    'AI控制程序员', '程序员自主性', 'AI替代决策', '代码工人'
]

# ============================================================================
# 3. 基础设施层 (INFRASTRUCTURE)
# ============================================================================

class DatabaseManager:
    """MongoDB 封装: 去重写入 + 匿名化 + 审计追踪"""

    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name]
        self.collection = self.db[RAW_COLLECTION]
        # 创建索引加速去重和查询 (后台执行，避免阻塞)
        try:
            # _id 是 MongoDB 自动创建的唯一索引，无需手动创建
            self.collection.create_index([("source", 1), ("phase", 1)], background=True)
            self.collection.create_index([("created_at", 1)], background=True)
            self.collection.create_index([("lang", 1)], background=True)
        except Exception as e:
            logger.warning(f"[DB] Index creation warning (may already exist): {e}")
        logger.info(f"[DB] Connected to {db_name}, collection: {RAW_COLLECTION}")

    @staticmethod
    def anonymize_username(username: Optional[str]) -> Optional[str]:
        """SHA256匿名化，保留可复现性 (加盐)"""
        if not username:
            return None
        salt = os.getenv("ANONYMIZE_SALT", "PE_LABOR_SALT_2024_v1")
        return hashlib.sha256(f"{username}_{salt}".encode()).hexdigest()[:16]

    @staticmethod
    def generate_id(doc: Dict) -> str:
        """基于URL + 内容前100字符生成唯一ID"""
        url = doc.get("url", "")
        text_prefix = doc.get("text", "")[:100]
        return hashlib.sha256(f"{url}_{text_prefix}".encode()).hexdigest()

    def insert(self, doc: Dict) -> bool:
        """
        插入单条文档，自动去重、匿名化、添加审计字段
        返回: True=成功/已存在, False=错误
        """
        try:
            # 生成唯一ID
            doc_id = self.generate_id(doc)
            doc["_id"] = doc_id

            # 匿名化作者
            if "author" in doc:
                doc["anonymized_author"] = self.anonymize_username(doc["author"])
                del doc["author"]  # 删除原始用户名

            # 审计字段
            doc["crawled_at"] = datetime.now(timezone.utc).isoformat()
            doc["version"] = "1.0"

            self.collection.insert_one(doc)
            return True

        except mongo_errors.DuplicateKeyError:
            # 已存在，跳过
            return True
        except Exception as e:
            logger.error(f"[DB] Insert error: {e}")
            return False

    def count(self, source: Optional[str] = None) -> int:
        """统计采集量"""
        query = {"source": source} if source else {}
        return self.collection.count_documents(query)

    def get_stats(self) -> Dict:
        """获取各源统计"""
        pipeline = [
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return {item["_id"]: item["count"] for item in self.collection.aggregate(pipeline)}

    def close(self):
        """关闭MongoDB连接"""
        try:
            self.client.close()
            logger.info("[DB] Connection closed.")
        except Exception as e:
            logger.warning(f"[DB] Close error: {e}")


class RequestManager:
    """请求管理: 会话保持、重试策略、UA轮换、代理预留"""

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    ]

    def __init__(self):
        self.session = requests.Session()
        # 重试策略: 对 429, 500, 502, 503, 504 指数退避
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,  # 2, 4, 8, 16, 32秒
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_headers(self, extra: Optional[Dict] = None) -> Dict:
        """生成请求头，带UA轮换"""
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
        }
        if extra:
            headers.update(extra)
        return headers

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.session.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.session.post(url, **kwargs)

    def close(self):
        """关闭HTTP会话"""
        self.session.close()


# 全局实例
req_manager = RequestManager()

# ============================================================================
# 4. GitHub 采集器 (GITHUB CRAWLER)
# ============================================================================

class GitHubCrawler:
    """
    GitHub GraphQL API v4 采集器
    采集对象: Discussions (讨论区，话语质量高) + Issues (带标签的问题讨论)

    Rate Limit: 
      - 每个Token 5000 points/hour
      - search 请求 cost 较高 (约10-30 points/次)
      - 策略: 多Token轮换 + 指数退避 + 预计算cost
    """

    ENDPOINT = "https://api.github.com/graphql"

    # GraphQL查询: 搜索Discussions
    DISCUSSION_QUERY = """
    query($query: String!, $first: Int!, $after: String) {
      search(query: $query, type: DISCUSSION, first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            ... on Discussion {
              id title bodyText createdAt url
              author { login }
              repository { nameWithOwner }
              comments(first: 100) {
                nodes { bodyText createdAt author { login } url }
              }
            }
          }
        }
      }
    }
    """

    # GraphQL查询: 搜索Issues (带评论)
    ISSUE_QUERY = """
    query($query: String!, $first: Int!, $after: String) {
      search(query: $query, type: ISSUE, first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            ... on Issue {
              id title bodyText createdAt url state
              author { login }
              repository { nameWithOwner }
              comments(first: 100) {
                nodes { bodyText createdAt author { login } url }
              }
            }
          }
        }
      }
    }
    """

    def __init__(self, tokens: List[str], db: DatabaseManager):
        if not tokens:
            raise ValueError("GitHub tokens empty! Set GITHUB_TOKEN_1~3 env vars.")
        self.tokens = tokens
        self.token_idx = 0
        self.db = db
        self.total_cost = 0  # 估算cost

    def _get_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.tokens[self.token_idx]}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v4+json"
        }

    def _rotate_token(self):
        """轮换Token"""
        old_idx = self.token_idx
        self.token_idx = (self.token_idx + 1) % len(self.tokens)
        logger.warning(f"[GitHub] Token rotated: {old_idx} -> {self.token_idx}")

    def _check_rate_limit(self, response_headers: Dict) -> bool:
        """检查剩余limit，如果过低则轮换。返回True表示可以继续使用当前Token。"""
        remaining = response_headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                if int(remaining) < 10:
                    logger.warning(f"[GitHub] Token {self.token_idx} rate limit low ({remaining}), rotating...")
                    self._rotate_token()
                    return False
            except ValueError:
                pass
        return True

    def _execute(self, query: str, variables: Dict) -> Optional[Dict]:
        """执行GraphQL请求，带错误处理和Token轮换

        重试策略:
          - 401 Unauthorized: 立即放弃（凭证错误，重试无用）
          - 403/429 RateLimit: 按reset时间等待后重试，并轮换Token
          - 500/502/503/504 + 网络错误: 指数退避重试
        """
        max_retries = max(len(self.tokens) * 2, 3)
        for attempt in range(max_retries):
            if _shutdown_requested:
                logger.info("[GitHub] Shutdown requested, aborting request.")
                return None

            try:
                resp = req_manager.post(
                    self.ENDPOINT,
                    json={"query": query, "variables": variables},
                    headers=self._get_headers(),
                    timeout=30
                )

                # 401: 认证失败，立即放弃，不重试
                if resp.status_code == 401:
                    logger.error(f"[GitHub] Token {self.token_idx} unauthorized (401), giving up.")
                    return None

                # 403/429: Rate limit，等待后重试
                if resp.status_code in (403, 429):
                    reset_time = resp.headers.get("X-RateLimit-Reset")
                    if reset_time:
                        wait = int(reset_time) - int(time.time()) + 5
                        wait = max(wait, 60)
                        wait = min(wait, 3600)
                    else:
                        wait = min(60 * (attempt + 1), 3600)
                    logger.warning(f"[GitHub] Rate limited (Token {self.token_idx}), waiting {wait}s...")
                    time.sleep(wait)
                    self._rotate_token()
                    continue

                resp.raise_for_status()
                self._check_rate_limit(resp.headers)

                data = resp.json()

                if "errors" in data:
                    logger.error(f"[GitHub] GraphQL errors: {data['errors']}")
                    return None

                return data

            except requests.exceptions.RequestException as e:
                logger.error(f"[GitHub] Request error (attempt {attempt+1}): {e}")
                time.sleep(min(2 ** attempt, 60))
                if len(self.tokens) > 0 and attempt % len(self.tokens) == 0:
                    self._rotate_token()

        logger.error("[GitHub] Max retries exceeded.")
        return None

    def _save_discussion(self, node: Dict, phase: str):
        """保存Discussion主帖和评论"""
        repo = node.get("repository", {}).get("nameWithOwner", "unknown/unknown")
        base_url = node.get("url", "")

        # 主帖
        self.db.insert({
            "source": "github_discussion",
            "phase": phase,
            "lang": "en",
            "url": base_url,
            "title": node.get("title", ""),
            "text": node.get("bodyText", ""),
            "created_at": node.get("createdAt", ""),
            "author": node.get("author", {}).get("login") if node.get("author") else None,
            "metadata": {
                "repo": repo,
                "type": "discussion",
                "node_id": node.get("id")
            }
        })

        # 评论
        for c in node.get("comments", {}).get("nodes", []):
            self.db.insert({
                "source": "github_comment",
                "phase": phase,
                "lang": "en",
                "url": c.get("url", base_url),
                "title": "",
                "text": c.get("bodyText", ""),
                "created_at": c.get("createdAt", ""),
                "author": c.get("author", {}).get("login") if c.get("author") else None,
                "metadata": {
                    "repo": repo,
                    "parent_type": "discussion",
                    "parent_id": node.get("id")
                }
            })

    def _save_issue(self, node: Dict, phase: str):
        """保存Issue主帖和评论"""
        repo = node.get("repository", {}).get("nameWithOwner", "unknown/unknown")
        base_url = node.get("url", "")

        # 只保存开放的或有讨论的Issue
        self.db.insert({
            "source": "github_issue",
            "phase": phase,
            "lang": "en",
            "url": base_url,
            "title": node.get("title", ""),
            "text": node.get("bodyText", ""),
            "created_at": node.get("createdAt", ""),
            "author": node.get("author", {}).get("login") if node.get("author") else None,
            "metadata": {
                "repo": repo,
                "state": node.get("state", "UNKNOWN"),
                "node_id": node.get("id")
            }
        })

        for c in node.get("comments", {}).get("nodes", []):
            self.db.insert({
                "source": "github_comment",
                "phase": phase,
                "lang": "en",
                "url": c.get("url", base_url),
                "title": "",
                "text": c.get("bodyText", ""),
                "created_at": c.get("createdAt", ""),
                "author": c.get("author", {}).get("login") if c.get("author") else None,
                "metadata": {
                    "repo": repo,
                    "parent_type": "issue",
                    "parent_id": node.get("id")
                }
            })

    def crawl_search(self, keyword: str, start_date: str, end_date: str, 
                     search_type: str = "DISCUSSION", max_pages: int = 20) -> int:
        """
        基于关键词和时间窗口采集

        Args:
            keyword: 搜索关键词
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            search_type: "DISCUSSION" or "ISSUE"
            max_pages: 最大页数 (每页50条)

        Returns:
            采集到的主帖数量
        """
        # 构建GraphQL search query
        # 注意: GitHub search 对时间过滤支持有限，主要靠created:范围
        q = f'{keyword} created:{start_date}..{end_date}'

        query = self.DISCUSSION_QUERY if search_type == "DISCUSSION" else self.ISSUE_QUERY
        phase = "B" if start_date >= "2024-03-01" else "A"

        cursor = None
        count = 0

        logger.info(f"[GitHub] Starting crawl: type={search_type}, kw={keyword}, phase={phase}")

        for page in range(max_pages):
            if _shutdown_requested:
                logger.info(f"[GitHub] Shutdown requested at page {page+1}, stopping.")
                break

            variables = {
                "query": q,
                "first": 50,
                "after": cursor
            }

            data = self._execute(query, variables)
            if not data or not data.get("data"):
                logger.error(f"[GitHub] No data returned at page {page}")
                break

            search_data = data["data"]["search"]
            edges = search_data.get("edges", [])

            if not edges:
                logger.info(f"[GitHub] No more results at page {page}")
                break

            for edge in edges:
                node = edge.get("node")
                if not node:
                    continue

                if search_type == "DISCUSSION":
                    self._save_discussion(node, phase)
                else:
                    self._save_issue(node, phase)
                count += 1

            logger.info(f"[GitHub] Page {page+1} done, nodes={len(edges)}, total={count}")

            # 分页检查
            page_info = search_data.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

            # 礼貌延迟 + cost估算
            time.sleep(2.5)

        logger.info(f"[GitHub] Crawl finished: {count} {search_type}s for '{keyword}'")
        return count

    def run_batch(self, keywords: List[str], start: str, end: str):
        """批量执行关键词"""
        total = 0
        for kw in keywords:
            if _shutdown_requested:
                logger.info("[GitHub] Shutdown requested, stopping batch.")
                break
            total += self.crawl_search(kw, start, end, "DISCUSSION", max_pages=15)
            total += self.crawl_search(kw, start, end, "ISSUE", max_pages=10)
            time.sleep(5)  # 关键词间隔
        logger.info(f"[GitHub] Batch total: {total}")


# ============================================================================
# 5. Hacker News 采集器 (HN CRAWLER)
# ============================================================================

class HNCrawler:
    """
    Hacker News Algolia Search API
    特点: 完全开放，无需Auth，无Rate Limit，返回评论全文
    API文档: https://hn.algolia.com/api
    """

    SEARCH_URL = "https://hn.algolia.com/api/v1/search"

    def __init__(self, db: DatabaseManager):
        self.db = db

    def crawl(self, keyword: str, start_ts: int, end_ts: int, max_hits: int = 1000) -> int:
        """
        按时间窗口采集评论 (支持Algolia分页)

        Args:
            keyword: 搜索词
            start_ts: Unix timestamp (秒)
            end_ts: Unix timestamp (秒)
            max_hits: 最大返回数 (API限制单次1000)

        Returns:
            采集评论数
        """
        phase = "B" if start_ts >= TS_PHASE_B_START else "A"
        count = 0
        page = 0
        hits_per_page = min(max_hits, 1000)
        max_pages = (max_hits + hits_per_page - 1) // hits_per_page

        logger.info(f"[HN] Searching: '{keyword}', ts={start_ts}~{end_ts}")

        while page < max_pages:
            if _shutdown_requested:
                logger.info(f"[HN] Shutdown requested at page {page}, stopping.")
                break

            params = {
                "query": keyword,
                "tags": "comment",
                "numericFilters": f"created_at_i>{start_ts},created_at_i<{end_ts}",
                "hitsPerPage": hits_per_page,
                "page": page
            }

            try:
                resp = req_manager.get(self.SEARCH_URL, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                hits = data.get("hits", [])
                nb_pages = data.get("nbPages", 1)

                if not hits:
                    break

                for h in hits:
                    # 清洗HTML标签
                    raw_text = h.get("text", "") or ""
                    text = BeautifulSoup(raw_text, "html.parser").get_text()

                    if not text or len(text) < 20:
                        continue

                    created_ts = h.get("created_at_i")
                    if created_ts is None:
                        continue
                    created_dt = datetime.fromtimestamp(created_ts, tz=timezone.utc)

                    object_id = h.get('objectID', '')
                    if not object_id:
                        continue

                    self.db.insert({
                        "source": "hackernews",
                        "phase": phase,
                        "lang": "en",
                        "url": f"https://news.ycombinator.com/item?id={object_id}",
                        "title": "",
                        "text": text,
                        "created_at": created_dt.isoformat(),
                        "author": h.get("author"),
                        "metadata": {
                            "points": h.get("points"),
                            "parent_id": h.get("parent_id"),
                            "story_id": h.get("story_id"),
                            "story_title": h.get("story_title", ""),
                            "search_keyword": keyword
                        }
                    })
                    count += 1

                logger.info(f"[HN] Page {page} saved {len(hits)} comments, total={count}")

                page += 1
                if page >= nb_pages:
                    break
                time.sleep(1)

            except Exception as e:
                logger.error(f"[HN] Error at page {page}: {e}")
                return count

        logger.info(f"[HN] Saved {count} comments for '{keyword}'")
        return count

    def run_batch(self, keywords: List[str], start_ts: int, end_ts: int):
        total = 0
        for kw in keywords:
            if _shutdown_requested:
                logger.info("[HN] Shutdown requested, stopping batch.")
                break
            total += self.crawl(kw, start_ts, end_ts)
            time.sleep(1)
        logger.info(f"[HN] Batch total: {total}")


# ============================================================================
# 6. Reddit 采集器 (REDDIT CRAWLER)
# ============================================================================

class RedditCrawler:
    """
    Reddit API via PRAW (Python Reddit API Wrapper)
    注意: Reddit API 限制 100 requests/min (OAuth后)
    如需大规模采集，建议配合 Pushshift API (第三方归档，免费)

    子版块选择依据 (程序员密度 + AI话题活跃度):
      - r/programming: 通用编程讨论
      - r/cscareerquestions: 职业焦虑核心场域
      - r/webdev: 前端/全栈工作流变化
      - r/MachineLearning: AI技术向讨论
      - r/LocalLLaMA: 本地AI工具使用体验
    """

    SUBREDDITS = ["programming", "cscareerquestions", "webdev", "MachineLearning", "LocalLLaMA"]

    def __init__(self, client_id: str, client_secret: str, user_agent: str, db: DatabaseManager):
        if not all([client_id, client_secret]):
            logger.warning("[Reddit] Credentials not set, Reddit crawler disabled.")
            self.reddit = None
        else:
            try:
                import praw
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent,
                    check_for_async=False
                )
                logger.info(f"[Reddit] Authenticated as: {self.reddit.user.me()}")
            except Exception as e:
                logger.error(f"[Reddit] Auth failed: {e}")
                self.reddit = None

        self.db = db

    def crawl_subreddit(self, sub_name: str, keyword: str, 
                        time_filter: str = "all", limit: int = 500) -> int:
        """
        搜索子版块中的帖子及评论
        time_filter: all, year, month, week
        """
        if not self.reddit:
            return 0

        subreddit = self.reddit.subreddit(sub_name)
        phase_boundary = datetime(2024, 3, 1, tzinfo=timezone.utc)
        count = 0

        logger.info(f"[Reddit] Searching r/{sub_name} for '{keyword}'")

        try:
            # 搜索帖子 (submission)
            for submission in subreddit.search(keyword, time_filter=time_filter, sort="new", limit=limit):
                if _shutdown_requested:
                    logger.info(f"[Reddit] Shutdown requested, stopping r/{sub_name} search.")
                    break
                created_dt = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                phase = "B" if created_dt >= phase_boundary else "A"

                self.db.insert({
                    "source": "reddit",
                    "phase": phase,
                    "lang": "en",
                    "url": f"https://reddit.com{submission.permalink}",
                    "title": submission.title,
                    "text": submission.selftext,
                    "created_at": created_dt.isoformat(),
                    "author": str(submission.author) if submission.author else None,
                    "metadata": {
                        "subreddit": sub_name,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "search_keyword": keyword
                    }
                })
                count += 1

                # 抓取Top评论 (最多50条，避免太深)
                try:
                    submission.comments.replace_more(limit=0)
                    for comment in list(submission.comments)[:50]:
                        if _shutdown_requested:
                            break
                        if not hasattr(comment, 'body'):
                            continue
                        c_created = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
                        c_phase = "B" if c_created >= phase_boundary else "A"

                        self.db.insert({
                            "source": "reddit_comment",
                            "phase": c_phase,
                            "lang": "en",
                            "url": f"https://reddit.com{comment.permalink}",
                            "title": "",
                            "text": comment.body,
                            "created_at": c_created.isoformat(),
                            "author": str(comment.author) if comment.author else None,
                            "metadata": {
                                "subreddit": sub_name,
                                "score": comment.score,
                                "parent_submission": submission.id,
                                "search_keyword": keyword
                            }
                        })
                        count += 1
                except Exception as e:
                    logger.warning(f"[Reddit] Comment crawl error: {e}")

                # 速率控制: Reddit限制100 req/min
                time.sleep(0.8)

        except Exception as e:
            logger.error(f"[Reddit] Search error in r/{sub_name}: {e}")

        logger.info(f"[Reddit] r/{sub_name} saved {count} items")
        return count

    def run_batch(self, keywords: List[str], time_filter: str = "all"):
        if not self.reddit:
            logger.warning("[Reddit] Skipped (no credentials)")
            return

        total = 0
        for sub in self.SUBREDDITS:
            for kw in keywords:
                if _shutdown_requested:
                    logger.info("[Reddit] Shutdown requested, stopping batch.")
                    break
                total += self.crawl_subreddit(sub, kw, time_filter, limit=300)
                time.sleep(2)
            if _shutdown_requested:
                break
        logger.info(f"[Reddit] Batch total: {total}")


# ============================================================================
# 7. V2EX 采集器 (V2EX CRAWLER)
# ============================================================================

class V2EXCrawler:
    """
    V2EX 技术社区采集器
    目标节点 (Nodes):
      - programmer: 程序员综合讨论
      - career: 职场话题 (职业焦虑集中地)
      - ai: 人工智能
      - create: 创业/独立开发 (劳动自主性)
      - python, js, go: 具体技术栈 (技能话语)

    特点: 页面结构极简，反爬弱，但需礼貌延迟
    策略: UA轮换 + Cookie维持 + 1.5-3秒延迟
    """

    TARGET_NODES = ["programmer", "career", "ai", "create", "python", "js", "go"]
    BASE_URL = "https://www.v2ex.com"

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.session = req_manager.session
        # V2EX需要维持Cookie会话
        self._init_session()

    def _init_session(self):
        """预访问首页获取Cookie"""
        try:
            resp = self.session.get(self.BASE_URL, headers=req_manager.get_headers(), timeout=10)
            logger.info(f"[V2EX] Session init: {resp.status_code}")
        except Exception as e:
            logger.warning(f"[V2EX] Session init failed: {e}")

    def _get_headers(self) -> Dict:
        """V2EX专用头"""
        return req_manager.get_headers({
            "Referer": "https://www.v2ex.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        })

    def parse_topic_page(self, topic_url: str, retries: int = 3) -> Optional[Dict]:
        """
        解析单个话题页，提取标题、正文、评论
        返回完整文档Dict，失败返回None
        """
        for attempt in range(retries):
            try:
                resp = self.session.get(topic_url, headers=self._get_headers(), timeout=15)
                if resp.status_code == 403 and attempt < retries - 1:
                    logger.warning(f"[V2EX] 403 for {topic_url}, retry {attempt+1}/{retries}...")
                    time.sleep(10)
                    continue
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if attempt < retries - 1:
                    logger.warning(f"[V2EX] Request error for {topic_url}, retry {attempt+1}/{retries}: {e}")
                    time.sleep(5)
                    continue
                logger.error(f"[V2EX] Parse error {topic_url}: {e}")
                return None
        else:
            return None

        try:
            soup = BeautifulSoup(resp.text, 'html.parser')

            # 标题
            title_tag = soup.select_one('h1')
            title = title_tag.text.strip() if title_tag else ""

            # 正文 (topic_content)
            content_div = soup.select_one('.topic_content')
            content = content_div.get_text(separator='\n', strip=True) if content_div else ""

            # 时间 (ago标签的title属性为ISO时间)
            ago_tag = soup.select_one('.ago')
            created = ""
            if ago_tag and ago_tag.has_attr('title'):
                created = ago_tag['title']  # 格式: 2024-05-08 10:30:00 +08:00

            # 评论列表
            comments = []
            for reply in soup.select('.reply_content'):
                c_text = reply.get_text(separator='\n', strip=True)
                if c_text:
                    comments.append(c_text)

            # 判断Phase
            phase = "unknown"
            if created:
                try:
                    dt = datetime.strptime(created[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    phase = "B" if dt >= datetime(2024, 3, 1, tzinfo=timezone.utc) else "A"
                except Exception:
                    pass

            return {
                "title": title,
                "content": content,
                "created_at": created,
                "phase": phase,
                "comments": comments,
                "url": topic_url
            }

        except Exception as e:
            logger.error(f"[V2EX] Parse error {topic_url}: {e}")
            return None

    def crawl_node(self, node_name: str, max_pages: int = 15) -> int:
        """
        采集某个节点下的帖子列表，并逐个解析详情页

        Args:
            node_name: V2EX节点名
            max_pages: 最大翻页数 (每页约20-30帖)
        """
        count = 0
        logger.info(f"[V2EX] Starting node: {node_name}, max_pages={max_pages}")

        for page in range(1, max_pages + 1):
            if _shutdown_requested:
                logger.info(f"[V2EX] Shutdown requested at page {page}, stopping.")
                break

            list_url = f"{self.BASE_URL}/go/{node_name}?p={page}"

            try:
                resp = self.session.get(list_url, headers=self._get_headers(), timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')

                items = soup.select('.item_title')
                if not items:
                    logger.info(f"[V2EX] Node {node_name} page {page} empty, stopping.")
                    break

                for item in items:
                    href = item.get('href', '')
                    if not href:
                        continue
                    topic_url = urljoin(self.BASE_URL, href)

                    # 解析详情页
                    topic_data = self.parse_topic_page(topic_url)
                    if not topic_data:
                        continue

                    # 保存主帖
                    self.db.insert({
                        "source": "v2ex",
                        "phase": topic_data["phase"],
                        "lang": "zh",
                        "url": topic_url,
                        "title": topic_data["title"],
                        "text": topic_data["content"],
                        "created_at": topic_data["created_at"],
                        "author": None,  # V2EX不采集用户名，更严格匿名
                        "metadata": {
                            "node": node_name,
                            "num_comments": len(topic_data["comments"])
                        }
                    })
                    count += 1

                    # 保存评论 (每条作为独立文档，便于NLP分析)
                    # 评论无独立时间戳，使用主帖时间+标记
                    for idx, c_text in enumerate(topic_data["comments"]):
                        self.db.insert({
                            "source": "v2ex_comment",
                            "phase": topic_data["phase"],
                            "lang": "zh",
                            "url": topic_url,
                            "title": "",
                            "text": c_text,
                            "created_at": topic_data["created_at"],
                            "author": None,
                            "metadata": {
                                "node": node_name,
                                "parent_url": topic_url,
                                "comment_index": idx,
                                "time_approximated": True  # 标记为近似时间
                            }
                        })
                        count += 1

                    # 帖子间延迟
                    time.sleep(random.uniform(1.5, 3.0))

                logger.info(f"[V2EX] Node {node_name} page {page} done, items={len(items)}")

                # 翻页延迟
                time.sleep(random.uniform(2, 4))

            except Exception as e:
                logger.error(f"[V2EX] Node {node_name} page {page} error: {e}")
                time.sleep(5)

        logger.info(f"[V2EX] Node {node_name} total saved: {count}")
        return count

    def run_batch(self):
        total = 0
        for node in self.TARGET_NODES:
            if _shutdown_requested:
                logger.info("[V2EX] Shutdown requested, stopping batch.")
                break
            total += self.crawl_node(node, max_pages=12)
            time.sleep(5)
        logger.info(f"[V2EX] Batch total: {total}")


# ============================================================================
# 8. 掘金 采集器 (JUEJIN CRAWLER)
# ============================================================================

class JuejinCrawler:
    """
    掘金 (juejin.cn) 采集器

    技术说明:
    掘金的搜索API有两种模式:
    1. 公开搜索API (api.juejin.cn/search_api/v1/search)
       - 需要 aid, uuid, signature (从浏览器抓包获取)
       - 有反爬，但结构规整
    2. 备用方案: 直接抓取搜索结果页HTML (无需API密钥，但稳定性差)

    抓包指南 (如何获取参数):
    1. 浏览器打开 https://juejin.cn/search?query=AI编程&fromSeo=1
    2. F12 -> Network -> 筛选 "search"
    3. 找到请求: POST https://api.juejin.cn/search_api/v1/search
    4. 复制请求中的 aid, uuid, signature (有时在Cookie或Body中)
    5. 这些参数有效期约1-7天，失效后需重新抓包

    如果无法获取签名，本类会自动降级为HTML抓取模式
    """

    SEARCH_API = "https://api.juejin.cn/search_api/v1/search"
    SEARCH_PAGE = "https://juejin.cn/search"

    def __init__(self, db: DatabaseManager, aid: str = "", uuid: str = "", signature: str = ""):
        self.db = db
        self.aid = aid
        self.uuid = uuid
        self.signature = signature
        self.use_api = bool(aid and uuid)

        if self.use_api:
            logger.info("[Juejin] API mode enabled")
        else:
            logger.warning("[Juejin] API credentials missing, will use HTML fallback (limited)")

    def _api_search(self, keyword: str, cursor: str = "0", limit: int = 20) -> Tuple[List[Dict], str]:
        """
        API模式搜索
        返回: (文章列表, 下一页cursor)
        """
        payload = {
            "key_word": keyword,
            "cursor": cursor,
            "limit": limit,
            "search_type": 0,  # 文章
            "sort_type": 0,   # 综合排序
            "aid": self.aid,
            "uuid": self.uuid
        }

        headers = req_manager.get_headers({
            "Content-Type": "application/json",
            "Referer": f"https://juejin.cn/search?query={quote(keyword)}",
            "Origin": "https://juejin.cn",
            "X-Signature": self.signature  # 部分版本在Header中
        })

        try:
            resp = req_manager.post(self.SEARCH_API, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("err_no") != 0:
                logger.warning(f"[Juejin] API error: {data.get('err_msg')}")
                return [], ""

            articles = []
            for item in data.get("data", []):
                model = item.get("result_model", {})
                info = model.get("article_info", {})

                # 时间戳转ISO
                ctime = info.get("ctime", 0)
                if not ctime:
                    continue
                created_dt = datetime.fromtimestamp(ctime, tz=timezone.utc)

                articles.append({
                    "article_id": model.get("article_id"),
                    "title": model.get("title", ""),
                    "brief_content": model.get("brief_content", ""),  # 摘要
                    "content": info.get("mark_content", ""),  # Markdown内容 (可能为空，需详情页)
                    "created_at": created_dt.isoformat(),
                    "tags": [t.get("tag_name") for t in model.get("tags", [])],
                    "user_name": model.get("user_name", "")  # 需匿名化
                })

            # 下一页cursor (掘金API使用数字偏移)
            try:
                next_cursor = str(int(cursor) + limit)
            except ValueError:
                next_cursor = ""
            return articles, next_cursor

        except Exception as e:
            logger.error(f"[Juejin] API request error: {e}")
            return [], ""

    def _html_search(self, keyword: str, page: int = 1) -> List[Dict]:
        """
        HTML备用模式: 直接抓取搜索结果页
        可靠性较低，仅作兜底
        """
        url = f"{self.SEARCH_PAGE}?query={quote(keyword)}&page={page}"
        try:
            resp = req_manager.get(url, headers=req_manager.get_headers({
                "Referer": "https://juejin.cn/"
            }), timeout=15)

            soup = BeautifulSoup(resp.text, 'html.parser')
            articles = []

            # 掘金搜索结果结构 (可能随前端更新变化)
            for item in soup.select('.search-item') or soup.select('[data-v-] .title'):  # 模糊匹配
                link = item if item.name == 'a' else item.find_parent('a')
                if not link:
                    continue
                href = link.get('href', '')
                title = item.get_text(strip=True)

                articles.append({
                    "article_id": href.split("/")[-1] if "/" in href else "",
                    "title": title,
                    "brief_content": "",
                    "content": "",
                    "created_at": "",
                    "tags": [],
                    "user_name": ""
                })

            return articles
        except Exception as e:
            logger.error(f"[Juejin] HTML fallback error: {e}")
            return []

    def _fetch_article_detail(self, article_id: str) -> str:
        """
        获取文章详情内容
        掘金文章API: https://api.juejin.cn/content_api/v1/article/detail
        """
        detail_url = "https://api.juejin.cn/content_api/v1/article/detail"
        payload = {
            "article_id": article_id,
            "aid": self.aid,
            "uuid": self.uuid
        }

        try:
            resp = req_manager.post(detail_url, json=payload, headers=req_manager.get_headers({
                "Content-Type": "application/json",
                "Referer": f"https://juejin.cn/post/{article_id}"
            }), timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("err_no") == 0:
                return data.get("data", {}).get("article_info", {}).get("mark_content", "")
        except Exception as e:
            logger.debug(f"[Juejin] Detail fetch error: {e}")

        return ""

    def crawl(self, keyword: str, max_results: int = 500) -> int:
        """
        采集掘金搜索结果

        Args:
            keyword: 搜索关键词
            max_results: 最大采集数
        """
        count = 0
        cursor = "0"
        phase_boundary = datetime(2024, 3, 1, tzinfo=timezone.utc)

        logger.info(f"[Juejin] Starting crawl for '{keyword}', max={max_results}")

        while count < max_results:
            if _shutdown_requested:
                logger.info(f"[Juejin] Shutdown requested, stopping.")
                break

            if self.use_api:
                articles, cursor = self._api_search(keyword, cursor, limit=20)
            else:
                # HTML模式一次抓一页
                page = (count // 20) + 1
                articles = self._html_search(keyword, page)
                try:
                    cursor = str(int(cursor) + 20) if articles else ""
                except ValueError:
                    cursor = ""

            if not articles:
                break

            for art in articles:
                # 时间解析
                created_str = art.get("created_at", "")
                phase = "unknown"
                try:
                    if created_str:
                        dt = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                        phase = "B" if dt >= phase_boundary else "A"
                except:
                    pass

                # 获取正文 (如果brief不够长)
                content = art.get("brief_content", "")
                if len(content) < 100 and art.get("article_id") and self.use_api:
                    detail = self._fetch_article_detail(art["article_id"])
                    if detail:
                        content = detail

                if not content or len(content) < 30:
                    continue

                self.db.insert({
                    "source": "juejin",
                    "phase": phase,
                    "lang": "zh",
                    "url": f"https://juejin.cn/post/{art.get('article_id', '')}",
                    "title": art.get("title", ""),
                    "text": content,
                    "created_at": created_str,
                    "author": art.get("user_name") if art.get("user_name") else None,
                    "metadata": {
                        "tags": art.get("tags", []),
                        "search_keyword": keyword
                    }
                })
                count += 1

            logger.info(f"[Juejin] Progress: {count}/{max_results}")
            time.sleep(random.uniform(2, 4))

            # 终止条件检查
            cursor_int = 0
            try:
                cursor_int = int(cursor)
            except ValueError:
                pass
            if not cursor or cursor == "0" or (self.use_api and cursor_int >= max_results * 2):
                break

        logger.info(f"[Juejin] Finished '{keyword}': {count} articles")
        return count

    def run_batch(self, keywords: List[str]):
        total = 0
        for kw in keywords:
            if _shutdown_requested:
                logger.info("[Juejin] Shutdown requested, stopping batch.")
                break
            total += self.crawl(kw, max_results=400)
            time.sleep(5)
        logger.info(f"[Juejin] Batch total: {total}")


# ============================================================================
# 9. 主控与调度 (MAIN CONTROLLER)
# ============================================================================

# 全局标志：用于SIGINT优雅退出 (使用 threading.Event 保证线程安全)
_shutdown_event = threading.Event()

def _is_shutdown_requested() -> bool:
    """线程安全地检查是否收到关闭信号"""
    return _shutdown_event.is_set()

# 兼容旧代码中的 _shutdown_requested 引用
_shutdown_requested = False

def _update_shutdown_flag():
    """同步更新旧全局变量以保持兼容性"""
    global _shutdown_requested
    _shutdown_requested = _shutdown_event.is_set()

def _signal_handler(signum, frame):
    logger.warning("[Main] Shutdown signal received, finishing current task...")
    _shutdown_event.set()
    _update_shutdown_flag()

# 注册信号处理 (Windows 对 SIGINT 支持有限，使用 try-except 兜底)
if sys.platform != "win32":
    signal.signal(signal.SIGINT, _signal_handler)
else:
    logger.info("[Main] Windows detected, SIGINT handler registered with fallback.")
    try:
        signal.signal(signal.SIGINT, _signal_handler)
    except (ValueError, OSError):
        logger.warning("[Main] SIGINT handler registration failed on Windows, using KeyboardInterrupt fallback.")

def main():
    """
    主执行函数
    建议运行方式:
      1. 设置环境变量 (MONGO_URI, GITHUB_TOKEN_1~3, REDDIT_CLIENT_ID等)
      2. python crawler.py
      3. 首次建议小批量测试 (修改main中的开关)
    """
    global _shutdown_requested

    logger.info("=" * 60)
    logger.info("Political Economy of AI Coding Labor - Crawler Startup")
    logger.info("=" * 60)

    # 初始化数据库
    try:
        db = DatabaseManager(MONGO_URI, DB_NAME)
        stats_before = db.get_stats()
        logger.info(f"[Init] DB stats before: {stats_before}")
    except Exception as e:
        logger.critical(f"[Init] DB connection failed: {e}")
        logger.critical("Please set MONGO_URI env var or check network.")
        return

    # ========== Phase A: 探索期 (2022-11 ~ 2024-02) ==========
    logger.info("\n>>> PHASE A: Exploration Period (2022-11 ~ 2024-02) <<<")

    # GitHub (EN)
    if GITHUB_TOKENS and not _shutdown_requested:
        gh = GitHubCrawler(GITHUB_TOKENS, db)
        gh.run_batch(KEYWORDS_EN[:5], "2022-11-30", "2024-02-29")  # 先测前5个关键词

    # Hacker News (EN)
    if not _shutdown_requested:
        hn = HNCrawler(db)
        hn.run_batch(
            ['copilot', 'ai coding', 'programmer jobs', 'replace programmers'],
            TS_PHASE_A_START, TS_PHASE_A_END
        )

    # Reddit (EN) - 需要凭证，可选
    if not _shutdown_requested:
        rd = RedditCrawler(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, db)
        rd.run_batch(KEYWORDS_EN[:3], time_filter="all")

    # V2EX (ZH)
    if not _shutdown_requested:
        v2 = V2EXCrawler(db)
        v2.run_batch()

    # 掘金 (ZH)
    if not _shutdown_requested:
        jj = JuejinCrawler(db, JUEJIN_AID, JUEJIN_UUID, JUEJIN_SIGNATURE)
        jj.run_batch(KEYWORDS_ZH[:5])

    # ========== Phase B: 范式震荡期 (2024-03 ~ 2026-05) ==========
    if _shutdown_requested:
        logger.info("[Main] Shutdown requested, skipping Phase B.")
    else:
        logger.info("\n>>> PHASE B: Paradigm Disruption (2024-03 ~ 2026-05) <<<")

        if GITHUB_TOKENS:
            gh_b = GitHubCrawler(GITHUB_TOKENS, db)
            gh_b.run_batch(KEYWORDS_EN[:5], "2024-03-01", "2026-05-08")

        if not _shutdown_requested:
            hn_b = HNCrawler(db)
            hn_b.run_batch(
                ['vibe coding', 'cursor editor', 'ai layoffs', 'junior developer dead'],
                TS_PHASE_B_START, TS_PHASE_B_END
            )

        if not _shutdown_requested:
            rd_b = RedditCrawler(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, db)
            rd_b.run_batch(KEYWORDS_EN[:3], time_filter="all")

    # V2EX 和 掘金 全量抓取后按时间过滤，无需分Phase重跑
    # (已在采集时通过created_at自动标记phase)

    # ========== 完成统计 ==========
    stats_after = db.get_stats()
    logger.info("\n" + "=" * 60)
    logger.info("CRAWL COMPLETE")
    logger.info(f"Stats after: {stats_after}")

    total_new = sum(stats_after.values()) - sum(stats_before.values())
    logger.info(f"Total new documents: {total_new}")
    logger.info("=" * 60)

    # 关闭资源
    try:
        db.close()
    except Exception:
        pass
    try:
        req_manager.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
