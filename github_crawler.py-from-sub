import os as _os
try:
    from _secrets import GITHUB_TOKEN
except ImportError:
    GITHUB_TOKEN = _os.environ.get("GITHUB_TOKEN", "")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Academic Acquisition System (GAAS) - AI Coding Workflow Crawler
采集GitHub上AI Coding工作流相关讨论的完整文本（正文+评论+Review Comments+Discussion）
支持：英文精准搜索（时间/仓库切片） + 中文仓库列举（本地过滤）
"""

import json
import time
import hashlib
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

# ==================== 配置区（可外部化为YAML） ====================

CONFIG = {
    "github": {
        # 优先使用 GitHub App 的 Installation Token；次选 Personal Access Token
        "token": GITHUB_TOKEN,
        "rate_limit": {
            "search_per_minute": 10,      # Search API: 10 req/min (authenticated)
            "rest_per_hour": 5000,        # REST API: 5000 req/hour
            "graphql_per_hour": 5000,     # GraphQL points/hour
            "sleep_buffer": 5,
        }
    },
    "output": {
        "dir": "./data",
        "checkpoint_file": "./checkpoint.json",
        "batch_size": 50,                # 每N条线程写入一次磁盘
    },
    "search": {
        "time_slice_days": 30,          # 英文查询时间切片粒度
        "max_results_per_query": 1000,  # GitHub硬顶
        "per_page": 100,
    },
    # 英文查询（工具+代码实践，无政治经济学词）
    # 注意：GitHub Search API 对带引号的精确匹配支持有限，
    # 使用不带引号的宽泛匹配效果更好
    "en_queries": [
        # 编写/生成
        'github copilot writing code',
        'cursor editor generating code',
        'vibe coding repository project',
        'agentic coding AI commits',
        'aider commit code',
        'trae IDE coding',
        # 审查
        'github copilot code review pull request',
        'cursor reviewing generated code',
        'vibe coding code review',
        # 调试
        'debugging copilot generated code',
        'fixing AI generated code bugs',
        'hallucinated code debugging',
        'AI slop generated code quality',
        # 工作流变化
        'not writing code copilot',
        'my workflow changed copilot',
        'used to write now review copilot',
        'YOLO commit AI generated code',
        'copy paste from AI coding',
        # 拼装/平台
        'stitching together copilot code',
        'glue code AI generated',
        'internal developer platform copilot',
        'scaffold code AI generated',
        'monorepo copilot generated',
        # 提交/测试/重构
        'copilot generating tests',
        'AI generated commit diff',
        'copilot refactoring code',
        # 质量
        'copilot generated code quality',
        'generated code technical debt',
        'cargo cult programming AI generated',
        # 学习
        'learning to code with copilot',
        'pair programming with AI workflow',
    ],
    "en_repos": [
        "cline/cline",
        "microsoft/vscode",
        "facebook/react",
        "angular/angular",
        "vercel/next.js",
        "oven-sh/bun",
        "nodejs/node",
        "withastro/astro",
    ],
    # 中文：仓库列举 + 本地过滤
    "zh_repos": [
        "alibaba/nacos",
        "alibaba/dubbo",
        "bytedance/monoio",
        "pingcap/tidb",
        "tencent/tdesign",
        "apache/shardingsphere",
    ],
    "zh_filter_keywords": [
        "copilot", "cursor", "cline", "aider", "trae",
        "通义灵码", "CodeGeeX", "Fitten Code",
        "AI编程", "AI写代码", "AI生成代码", "vibe coding", "氛围编程",
        "代码审查", "调试", "重构", "合并", "中台", "内部平台",
        "脚手架", "胶水代码", "拼装", "标准化", "提示词工程", "prompt工程",
    ],
}

# ==================== 日志 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("crawler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("gaas")


# ==================== 数据模型 ====================

@dataclass
class ThreadRecord:
    thread_id: str                # owner/repo/type/number
    source: Dict
    original_post: Dict
    comments: List[Dict] = field(default_factory=list)
    pr_review_comments: List[Dict] = field(default_factory=list)
    discussion_replies: List[Dict] = field(default_factory=list)
    query_tags: List[str] = field(default_factory=list)
    hit_keywords: List[str] = field(default_factory=list)
    dedup_count: int = 1
    completeness_issues: List[str] = field(default_factory=list)
    is_complete: bool = False
    fetched_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


# ==================== 速率限制管理器 ====================

class RateLimiter:
    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self.search_last = 0
        self.rest_last = 0
        self.graphql_last = 0
        self.rest_remaining = cfg["rest_per_hour"]
        self.graphql_remaining = cfg["graphql_per_hour"]

    def sleep_search(self):
        elapsed = time.time() - self.search_last
        needed = 60.0 / self.cfg["search_per_minute"] + 1  # 留1秒余量
        if elapsed < needed:
            time.sleep(needed - elapsed)
        self.search_last = time.time()

    def sleep_rest(self, resp: Optional[requests.Response] = None):
        if resp:
            self.rest_remaining = int(resp.headers.get("X-RateLimit-Remaining", self.rest_remaining))
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 3600))
            if self.rest_remaining <= 5:
                sleep = max(reset_ts - time.time(), 0) + self.cfg["sleep_buffer"]
                logger.warning(f"REST rate limit nearly exhausted. Sleeping {sleep:.0f}s...")
                time.sleep(sleep)
        else:
            elapsed = time.time() - self.rest_last
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)
        self.rest_last = time.time()

    def sleep_graphql(self, resp: Optional[requests.Response] = None):
        if resp:
            self.graphql_remaining = int(resp.headers.get("X-RateLimit-Remaining", self.graphql_remaining))
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 3600))
            if self.graphql_remaining <= 100:
                sleep = max(reset_ts - time.time(), 0) + self.cfg["sleep_buffer"]
                logger.warning(f"GraphQL rate limit nearly exhausted. Sleeping {sleep:.0f}s...")
                time.sleep(sleep)


# ==================== GitHub API 客户端 ====================

class GitHubClient:
    def __init__(self, token: str, limiter: RateLimiter):
        self.token = token
        self.limiter = limiter
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Academic-IPE-AICoding-Study/1.0",
        }
        self.graphql_url = "https://api.github.com/graphql"
        self.rest_url = "https://api.github.com"

    # ---- REST 通用 ----
    def rest_get(self, endpoint: str, params: Optional[Dict] = None) -> Tuple[Dict, requests.Response]:
        url = f"{self.rest_url}{endpoint}"
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.limiter.sleep_rest()
                resp = requests.get(url, headers=self.headers, params=params or {}, timeout=60)
                self.limiter.sleep_rest(resp)
                if resp.status_code == 200:
                    return resp.json(), resp
                elif resp.status_code == 404:
                    return {}, resp
                elif resp.status_code == 410:
                    return {}, resp  # Gone
                else:
                    logger.error(f"REST GET {url} failed: {resp.status_code} - {resp.text[:200]}")
                    return {}, resp
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.Timeout) as e:
                logger.warning(f"REST GET attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"All {max_retries} attempts failed for {url}")
                    return {}, None

    # ---- Search API ----
    def search_issues(self, query: str, page: int = 1, per_page: int = 100) -> Tuple[List[Dict], bool]:
        """
        返回: (items列表, has_more)
        """
        self.limiter.sleep_search()
        params = {"q": query, "sort": "created", "order": "desc", "per_page": per_page, "page": page}
        # 带重试的请求
        max_retries = 5
        for attempt in range(max_retries):
            try:
                resp = requests.get(f"{self.rest_url}/search/issues", headers=self.headers, params=params, timeout=60)
                if resp.status_code != 200:
                    logger.error(f"Search failed: {resp.status_code} - {resp.text[:200]}")
                    return [], False
                data = resp.json()
                items = data.get("items", [])
                total = data.get("total_count", 0)
                has_more = (page * per_page) < min(total, 1000)  # 硬顶1000
                return items, has_more
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.Timeout) as e:
                logger.warning(f"Search attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"All {max_retries} attempts failed for search query")
                    return [], False

    # ---- 深度单线程拉取 ----
    def fetch_issue_body(self, owner: str, repo: str, number: int) -> Tuple[Optional[Dict], int]:
        """拉取Issue/PR正文，返回(data, expected_comments_count)"""
        data, resp = self.rest_get(f"/repos/{owner}/{repo}/issues/{number}")
        if not data:
            return None, 0
        expected_comments = data.get("comments", 0)
        return data, expected_comments

    def fetch_issue_comments(self, owner: str, repo: str, number: int) -> List[Dict]:
        """分页拉取普通评论（Issue/PR通用）"""
        comments = []
        page = 1
        while True:
            data, resp = self.rest_get(
                f"/repos/{owner}/{repo}/issues/{number}/comments",
                params={"per_page": 100, "page": page}
            )
            if not isinstance(data, list):
                break
            for c in data:
                comments.append({
                    "id": c["id"],
                    "author": c.get("user", {}).get("login", ""),
                    "body": c.get("body", ""),
                    "created_at": c.get("created_at", ""),
                    "updated_at": c.get("updated_at", ""),
                    "html_url": c.get("html_url", ""),
                })
            if len(data) < 100:
                break
            page += 1
            if page > 10:  # 安全阀，理论上100条/页 × 10页 = 1000条评论上限
                logger.warning(f"Comments pagination exceeded 10 pages for {owner}/{repo}/issues/{number}")
                break
        return comments

    def fetch_pr_review_comments(self, owner: str, repo: str, number: int) -> List[Dict]:
        """分页拉取PR行级Review Comments（仅PR）"""
        reviews = []
        page = 1
        while True:
            data, resp = self.rest_get(
                f"/repos/{owner}/{repo}/pulls/{number}/comments",
                params={"per_page": 100, "page": page}
            )
            if not isinstance(data, list):
                break
            for r in data:
                user = r.get("user") or {}
                reviews.append({
                    "id": r["id"],
                    "author": user.get("login", ""),
                    "body": r.get("body", ""),
                    "path": r.get("path", ""),
                    "line": r.get("line"),
                    "original_line": r.get("original_line"),
                    "diff_hunk": r.get("diff_hunk", ""),
                    "commit_id": r.get("commit_id", ""),
                    "created_at": r.get("created_at", ""),
                    "updated_at": r.get("updated_at", ""),
                })
            if len(data) < 100:
                break
            page += 1
            if page > 10:
                break
        return reviews

    def fetch_discussion_graphql(self, owner: str, repo: str, number: int) -> Optional[Dict]:
        """GraphQL拉取Discussion正文+评论+嵌套回复"""
        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            discussion(number: $number) {
              title
              bodyText
              createdAt
              author { login }
              comments(first: 100) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  id
                  bodyText
                  author { login }
                  createdAt
                  replies(first: 100) {
                    pageInfo { hasNextPage endCursor }
                    nodes {
                      id
                      bodyText
                      author { login }
                      createdAt
                    }
                  }
                }
              }
            }
          }
        }
        """
        variables = {"owner": owner, "repo": repo, "number": number}
        self.limiter.sleep_rest()
        resp = requests.post(
            self.graphql_url,
            headers={**self.headers, "Accept": "application/vnd.github.v4+json"},
            json={"query": query, "variables": variables},
            timeout=30,
        )
        self.limiter.sleep_graphql(resp)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if "errors" in data:
            logger.warning(f"GraphQL errors: {data['errors']}")
            return None
        return data.get("data", {}).get("repository", {}).get("discussion")

    def list_repo_issues(self, owner: str, repo: str, since: str, page: int = 1) -> List[Dict]:
        """列举仓库Issue（用于中文采集）"""
        try:
            data, resp = self.rest_get(
                f"/repos/{owner}/{repo}/issues",
                params={"state": "all", "since": since, "per_page": 100, "page": page}
            )
            if not isinstance(data, list):
                return []
            return data
        except Exception as e:
            logger.error(f"list_repo_issues error for {owner}/{repo} page {page}: {e}")
            return []


# ==================== 去重与合并 ====================

class ThreadDeduplicator:
    def __init__(self):
        self.seen: Dict[str, ThreadRecord] = {}

    @staticmethod
    def make_key(owner: str, repo: str, thread_type: str, number: int) -> str:
        return f"{owner}/{repo}/{thread_type}/{number}"

    def merge_or_create(self, record: ThreadRecord) -> Tuple[bool, ThreadRecord]:
        """
        返回: (is_new, final_record)
        """
        if record.thread_id in self.seen:
            existing = self.seen[record.thread_id]
            # 合并标签
            existing.query_tags = list(set(existing.query_tags + record.query_tags))
            existing.hit_keywords = list(set(existing.hit_keywords + record.hit_keywords))
            existing.dedup_count += 1
            return False, existing
        else:
            self.seen[record.thread_id] = record
            return True, record

    def get_all(self) -> List[ThreadRecord]:
        return list(self.seen.values())


# ==================== 完整性校验 ====================

class CompletenessValidator:
    @staticmethod
    def validate(record: ThreadRecord, expected_comments: int) -> ThreadRecord:
        issues = []

        # 1. 普通评论数校验
        actual_comments = len(record.comments)
        if expected_comments > 0 and actual_comments != expected_comments:
            issues.append(f"comment_count_mismatch: expected {expected_comments}, got {actual_comments}")

        # 2. 正文非空校验
        body = record.original_post.get("body", "")
        if not body or len(body) < 20:
            issues.append("body_too_short_or_empty")

        # 3. PR应有Review Comments（至少检查0条是合理的，但标记）
        if record.source.get("type") == "pull" and not record.pr_review_comments:
            # 很多PR确实没有Review Comments，仅作提示性issue
            pass

        # 4. Discussion嵌套校验（在采集阶段已递归，这里仅标记是否有回复）
        if record.source.get("type") == "discussion":
            if not record.discussion_replies and record.comments:
                issues.append("discussion_replies_not_fully_expanded")

        record.completeness_issues = issues
        record.is_complete = len(issues) == 0
        return record


# ==================== 主采集引擎 ====================

class AcquisitionEngine:
    def __init__(self, config: Dict):
        self.cfg = config
        self.client = GitHubClient(config["github"]["token"], RateLimiter(config["github"]["rate_limit"]))
        self.dedup = ThreadDeduplicator()
        self.validator = CompletenessValidator()
        self.output_dir = Path(config["output"]["dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = Path(config["output"]["checkpoint_file"])
        self.seen_thread_ids: Set[str] = self._load_checkpoint()
        self.batch_buffer: List[Dict] = []

    def _load_checkpoint(self) -> Set[str]:
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("completed_thread_ids", []))
        return set()

    def _save_checkpoint(self):
        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump({
                "completed_thread_ids": list(self.seen_thread_ids),
                "last_save": datetime.utcnow().isoformat(),
            }, f, ensure_ascii=False, indent=2)

    def _flush_batch(self):
        if not self.batch_buffer:
            return
        out_path = self.output_dir / f"threads_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for item in self.batch_buffer:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info(f"Flushed {len(self.batch_buffer)} threads to {out_path}")
        self.batch_buffer = []
        self._save_checkpoint()

    def _add_to_batch(self, record: ThreadRecord):
        self.batch_buffer.append(record.to_dict())
        if len(self.batch_buffer) >= self.cfg["output"]["batch_size"]:
            self._flush_batch()

    def _build_time_slices(self, start_str: str, end_str: str, days: int) -> List[str]:
        slices = []
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d")
        current = start
        while current < end:
            slice_end = min(current + timedelta(days=days), end)
            slices.append(f"{current.strftime('%Y-%m-%d')}..{slice_end.strftime('%Y-%m-%d')}")
            current = slice_end + timedelta(days=1)
        return slices

    def _parse_search_item(self, item: Dict) -> Optional[Tuple[str, str, str, int]]:
        """解析Search API返回的item，提取(owner, repo, type, number)"""
        html_url = item.get("html_url", "")
        # URL格式: https://github.com/owner/repo/issues/123 或 /pull/123
        parts = html_url.replace("https://github.com/", "").split("/")
        if len(parts) < 4:
            return None
        owner, repo = parts[0], parts[1]
        # 判断类型：PR也是Issue，但URL含/pull/
        thread_type = "pull" if "/pull/" in html_url else "issue"
        try:
            number = int(parts[-1])
        except ValueError:
            return None
        return owner, repo, thread_type, number

    def _fetch_full_thread(self, owner: str, repo: str, thread_type: str, number: int) -> Optional[ThreadRecord]:
        """深度拉取单线程完整文本"""
        thread_id = ThreadDeduplicator.make_key(owner, repo, thread_type, number)
        if thread_id in self.seen_thread_ids:
            return None  # 已完整采集过

        # Step 1: 正文 + expected_comments
        body_data, expected_comments = self.client.fetch_issue_body(owner, repo, number)
        if not body_data:
            return None

        original_post = {
            "title": body_data.get("title", ""),
            "body": body_data.get("body", ""),
            "author": body_data.get("user", {}).get("login", ""),
            "created_at": body_data.get("created_at", ""),
            "updated_at": body_data.get("updated_at", ""),
            "state": body_data.get("state", ""),
            "reactions": body_data.get("reactions", {}),
        }

        record = ThreadRecord(
            thread_id=thread_id,
            source={
                "owner": owner,
                "repo": repo,
                "type": thread_type,
                "number": number,
                "url": body_data.get("html_url", ""),
                "fetched_at": datetime.utcnow().isoformat(),
            },
            original_post=original_post,
        )

        # Step 2: 普通评论（Issue/PR通用）
        record.comments = self.client.fetch_issue_comments(owner, repo, number)

        # Step 3: PR额外拉Review Comments
        if thread_type == "pull":
            record.pr_review_comments = self.client.fetch_pr_review_comments(owner, repo, number)

        # Step 4: Discussion（如果正文数据暗示是Discussion，但Search API通常不返回Discussion；这里主要是防御性）
        # Discussion通常需要通过GraphQL单独搜索，不在Search Issues中

        # Step 5: 校验
        record = self.validator.validate(record, expected_comments)
        self.seen_thread_ids.add(thread_id)
        return record

    # ==================== 英文采集 ====================
    def run_en_acquisition(self, start_date: str = "2024-01-01", end_date: str = "2026-05-11", start_idx: int = 1):
        slices = self._build_time_slices(start_date, end_date, self.cfg["search"]["time_slice_days"])
        repos = self.cfg["en_repos"]
        queries = self.cfg["en_queries"]

        total_queries = len(queries) * len(repos) * len(slices)
        logger.info(f"英文采集计划: {len(queries)} queries × {len(repos)} repos × {len(slices)} slices = {total_queries} 次搜索")

        query_idx = 0
        for base_query in queries:
            for repo in repos:
                for tslice in slices:
                    query_idx += 1
                    if query_idx < start_idx:
                        continue
                    # 组装最终查询
                    final_query = f"{base_query} repo:{repo} created:{tslice}"
                    logger.info(f"[{query_idx}/{total_queries}] Searching: {final_query[:80]}...")

                    page = 1
                    while True:
                        items, has_more = self.client.search_issues(final_query, page=page, per_page=self.cfg["search"]["per_page"])
                        if not items:
                            break

                        for item in items:
                            parsed = self._parse_search_item(item)
                            if not parsed:
                                continue
                            owner, repo_name, thread_type, number = parsed

                            # 深度拉取
                            record = self._fetch_full_thread(owner, repo_name, thread_type, number)
                            if record is None:
                                # 可能已采集过，仅合并标签
                                thread_id = ThreadDeduplicator.make_key(owner, repo_name, thread_type, number)
                                tmp = ThreadRecord(
                                    thread_id=thread_id,
                                    source={},
                                    original_post={},
                                    query_tags=[base_query],
                                    hit_keywords=[],
                                )
                                is_new, merged = self.dedup.merge_or_create(tmp)
                                if not is_new:
                                    continue
                                else:
                                    # 未完整采集过但解析失败，跳过
                                    continue
                            else:
                                record.query_tags = [base_query]
                                record.hit_keywords = base_query.replace('"', "").split()
                                is_new, merged = self.dedup.merge_or_create(record)
                                if is_new:
                                    self._add_to_batch(merged)

                        if not has_more:
                            break
                        page += 1
                        if page > 10:  # 100条/页 × 10页 = 1000硬顶
                            break

        self._flush_batch()
        logger.info("英文采集完成")

    # ==================== 中文采集 ====================
    def run_zh_acquisition(self, since: str = "2024-01-01T00:00:00Z"):
        repos = self.cfg["zh_repos"]
        keywords = [k.lower() for k in self.cfg["zh_filter_keywords"]]
        logger.info(f"中文采集计划: {len(repos)} 仓库，过滤关键词 {len(keywords)} 个")

        for repo in repos:
            owner, name = repo.split("/")
            logger.info(f"列举仓库Issue: {repo}")
            page = 1
            while True:
                issues = self.client.list_repo_issues(owner, name, since, page)
                if not issues:
                    break

                for issue in issues:
                    # 本地过滤：标题或正文含任一关键词
                    title = issue.get("title", "").lower()
                    body = (issue.get("body") or "").lower()
                    combined = title + " " + body

                    matched = [k for k in keywords if k in combined]
                    if not matched:
                        continue

                    number = issue["number"]
                    thread_type = "pull" if "pull_request" in issue else "issue"
                    thread_id = ThreadDeduplicator.make_key(owner, name, thread_type, number)

                    if thread_id in self.seen_thread_ids:
                        # 仅合并标签
                        tmp = ThreadRecord(thread_id=thread_id, source={}, original_post={}, query_tags=["zh_local_filter"], hit_keywords=matched)
                        self.dedup.merge_or_create(tmp)
                        continue

                    # 深度拉取
                    record = self._fetch_full_thread(owner, name, thread_type, number)
                    if record:
                        record.query_tags = ["zh_local_filter"]
                        record.hit_keywords = matched
                        is_new, merged = self.dedup.merge_or_create(record)
                        if is_new:
                            self._add_to_batch(merged)

                if len(issues) < 100:
                    break
                page += 1

        self._flush_batch()
        logger.info("中文采集完成")

    def export_final(self):
        """导出最终去重后的全部数据"""
        all_records = self.dedup.get_all()
        out_path = self.output_dir / "final_merged_threads.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for r in all_records:
                f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
        logger.info(f"最终导出: {len(all_records)} 条唯一线程 → {out_path}")


# ==================== 入口 ====================

def main():
    engine = AcquisitionEngine(CONFIG)
    # 英文采集已完成（6944/6944），跳过，直接跑中文
    # engine.run_en_acquisition(start_date="2024-01-01", end_date="2026-05-11", start_idx=1)
    # 中文采集（仓库列举补充）
    engine.run_zh_acquisition(since="2024-01-01T00:00:00Z")
    # 导出最终合并数据
    engine.export_final()
    logger.info("全部采集完成")


if __name__ == "__main__":
    main()
