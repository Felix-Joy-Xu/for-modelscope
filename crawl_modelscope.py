#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
魔搭社区 (ModelScope) 爬虫
===========================
目标: 爬取魔搭社区关于 AI 编程的讨论，分析 AI 编程对程序员工作的影响

数据源:
  Source A - 研习社 (modelscope.cn/learn): 官方技术文章/教程
  Source B - CSDN社区 (modelscope.csdn.net): 社区讨论/问答

输出:
  - modelscope_articles.csv:    文章列表（含元数据）
  - modelscope_details/:        详情页 JSON（含全文+评论）
  - modelscope_state.json:      爬取状态（断点续爬）

时间窗口:
  Phase A (探索期): 2022-11-30 ~ 2024-02-29
  Phase B (范式震荡期): 2024-03-01 ~ 至今
"""

import csv
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ============================================================================
# 配置
# ============================================================================

# 输出目录
OUTPUT_DIR = Path(__file__).parent / "modelscope_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 文件路径
CSV_FILE = OUTPUT_DIR / "modelscope_articles.csv"
JSON_DIR = OUTPUT_DIR / "details"
STATE_FILE = OUTPUT_DIR / "modelscope_state.json"

# 请求配置
DELAY = 1.5              # 请求间隔（秒）
MAX_WORKERS = 3          # 详情页并发数
TIMEOUT = 30             # 请求超时（秒）

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/html, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.modelscope.cn/',
}

# Phase 时间边界
PHASE_B_BOUNDARY = datetime(2024, 3, 1, tzinfo=timezone.utc)

# ============================================================================
# 关键词体系（政治经济学视角）
# ============================================================================

# 研习社文章仅275篇，全部采集后在分析阶段过滤
# 关键词留作后置过滤参考
SOURCE_A_KEYWORDS = []  # 空=采集全部

# Source B 使用首页直接抓取，关键词留作分析阶段使用
SOURCE_B_KEYWORDS = []


# ============================================================================
# 工具函数
# ============================================================================

def classify_phase(dt: Optional[datetime]) -> str:
    if dt is None:
        return "unknown"
    if dt < PHASE_B_BOUNDARY:
        return "A"  # 探索期
    return "B"  # 范式震荡期


def ensure_json_dir():
    JSON_DIR.mkdir(exist_ok=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "source_a_page": 0,
        "source_a_total": 0,
        "source_a_article_ids": [],
        "source_b_completed_urls": [],
        "completed_detail_urls": [],
    }


def save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def safe_request(url: str, session: requests.Session, headers: dict = None,
                 timeout: int = TIMEOUT, max_retries: int = 3,
                 params: dict = None) -> Optional[requests.Response]:
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=headers or HEADERS, timeout=timeout, params=params)
            if resp.status_code == 200:
                return resp
            elif resp.status_code in (429, 503):
                wait = min(2 ** attempt * 5, 60)
                time.sleep(wait)
                continue
            else:
                time.sleep(2)
                continue
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt * 3)
                continue
    return None


# ============================================================================
# Source A: 研习社 (modelscope.cn/learn)
# ============================================================================

class LearnCrawler:
    """研习社文章列表 + 详情爬取"""

    LIST_API = "https://www.modelscope.cn/api/v1/articles"

    def __init__(self, session: requests.Session, state: dict):
        self.session = session
        self.state = state

    def crawl(self, keywords: List[str] = None) -> List[dict]:
        """爬取研习社文章，遍历所有页面（keywords=None 时采集全部）"""
        all_articles = []
        start_page = self.state.get("source_a_page", 0)
        seen_ids = set(self.state.get("source_a_article_ids", []))

        print(f"[研习社] 开始爬取，起始页码={start_page}")

        # 注意: API 分页参数无效，始终返回最近 10 篇
        params = {
            "page": 1,
            "size": 20,
            "sort": "gmt_modified",
        }
        resp = safe_request(self.LIST_API, self.session, params=params)
        if resp is None:
            print("  [研习社] 请求失败")
            return all_articles

        try:
            data = resp.json()
        except json.JSONDecodeError:
            print("  [研习社] JSON 解析失败")
            return all_articles

        if not data.get("Success"):
            print(f"  [研习社] API 返回失败: {data.get('Message')}")
            return all_articles

        articles = data.get("Data", {}).get("Articles", [])

        for art in articles:
            aid = art.get("Id")
            if aid in seen_ids:
                continue
            seen_ids.add(aid)

            gmt_published = art.get("GmtPublished", 0)
            dt = datetime.fromtimestamp(gmt_published, tz=timezone.utc) if gmt_published else None

            record = {
                "source": "modelscope_learn",
                "article_id": aid,
                "title": art.get("Title", ""),
                "title_en": art.get("TitleEn", ""),
                "description": art.get("Desc", ""),
                "description_en": art.get("DescEn", ""),
                "url": art.get("Url", ""),
                "content_url": art.get("ContentUrl", ""),
                "author_name": art.get("NickName") or art.get("CreatedBy", ""),
                "author_id": art.get("CreatedBy", ""),
                "avatar": art.get("Avatar", ""),
                "created_at": dt.isoformat() if dt else "",
                "timestamp": gmt_published,
                "click_count": art.get("Click", 0),
                "stars": art.get("Stars", 0),
                "is_pgc": art.get("IsPGC", False),
                "is_course": art.get("IsCourse", 0),
                "is_top": art.get("IsTop", 0),
                "content_type": art.get("ContentType", ""),
                "domains": art.get("Domains", "[]"),
                "subjects": art.get("Subjects", "[]"),
                "phase": classify_phase(dt),
                "keyword_matched": "",
            }
            all_articles.append(record)

        print(f"  [研习社] 获取 {len(articles)} 篇 (API 总计 {data.get('Data',{}).get('TotalCount','?')})")

        self.state["source_a_page"] = 1
        self.state["source_a_article_ids"] = list(seen_ids)
        save_state(self.state)

        self.state["source_a_total"] = len(all_articles)
        save_state(self.state)
        print(f"[研习社] 完成，共爬取 {len(all_articles)} 篇文章")
        return all_articles




# ============================================================================
# Source B: CSDN社区 (modelscope.csdn.net)
# ============================================================================

class CSDNCommunityCrawler:
    """CSDN DevPress 社区爬虫（魔搭社区在 CSDN 的镜像）"""

    BASE_URL = "https://modelscope.csdn.net"

    def __init__(self, session: requests.Session, state: dict):
        self.session = session
        self.state = state

    def _extract_initial_state(self, html: str) -> dict:
        import re
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return {}
        return {}

    def crawl_list(self) -> List[dict]:
        """从 modelscope.csdn.net 首页爬取文章列表（使用 __INITIAL_STATE__）"""
        import re

        all_articles = []
        seen_urls = set(self.state.get("source_b_completed_urls", []))

        print(f"[CSDN社区] 开始爬取首页文章列表")

        resp = safe_request(self.BASE_URL, self.session, timeout=15)
        if resp is None:
            print("  [CSDN社区] 首页请求失败")
            return []

        state_data = self._extract_initial_state(resp.text)
        page_data = state_data.get('pageData', {})

        # 合并多个文章列表源
        article_sources = [
            ('articles', page_data.get('articles', [])),
            ('topArticleList', page_data.get('topArticleList', [])),
            ('bottomArticleList', page_data.get('bottomArticleList', [])),
            ('headlines', page_data.get('headlines', [])),
        ]

        source_count = 0
        for source_name, items in article_sources:
            for item in items:
                if not isinstance(item, dict):
                    continue
                article_id = item.get('id', '') or item.get('articleId', '')
                if not article_id:
                    continue

                url = f"https://modelscope.csdn.net/{article_id}.html"
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = item.get('name', '') or item.get('title', '')
                desc = item.get('desc', '') or item.get('description', '')
                created_time = item.get('createdTime', '') or item.get('gmtCreated', '')

                dt = None
                if created_time:
                    try:
                        dt = datetime.strptime(created_time[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except (ValueError, IndexError):
                        pass

                author_data = item.get('author', {}) or {}
                author_name = author_data.get('nickname', '') or author_data.get('username', '')

                record = {
                    "source": "modelscope_csdn",
                    "article_id": article_id,
                    "title": title,
                    "url": url,
                    "description": desc,
                    "author_name": author_name,
                    "created_at": created_time[:19] if created_time else '',
                    "timestamp": dt.timestamp() if dt else 0,
                    "phase": classify_phase(dt),
                    "comment_count": (item.get('externalData') or {}).get('commentCount', 0),
                    "digg": (item.get('externalData') or {}).get('diggCount', 0),
                    "view": 0,
                }
                all_articles.append(record)
                source_count += 1

            if items:
                print(f"  [CSDN社区] {source_name}: {len(items)} 条, 新增 {source_count} 条")
                source_count = 0

        self.state["source_b_completed_urls"] = list(seen_urls)
        save_state(self.state)
        print(f"  [CSDN社区] 共提取 {len(all_articles)} 篇文章")
        return all_articles

    def _extract_initial_state(self, html: str) -> dict:
        """从页面提取 __INITIAL_STATE__ JSON"""
        import re
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return {}
        return {}

    def fetch_detail(self, article: dict) -> Optional[dict]:
        """抓取文章详情（全文 + 评论元数据）"""
        url = article.get("url", "")
        if not url:
            return None

        completed = set(self.state.get("completed_detail_urls", []))
        if url in completed:
            return None

        resp = safe_request(url, self.session, timeout=15)
        if resp is None:
            return None

        detail = dict(article)
        detail["full_content"] = ""
        detail["word_count"] = 0
        detail["read_time"] = 0
        detail["comment_count_actual"] = 0
        detail["digg_count"] = 0

        try:
            state_data = self._extract_initial_state(resp.text)
            page_data = state_data.get('pageData') or state_data.get('content', {})

            # 从 __INITIAL_STATE__ 提取内容
            detail_data = page_data.get('detail', {})
            ext = detail_data.get('ext', {})
            content_html = ext.get('content', '') if isinstance(ext, dict) else ''
            if content_html:
                content_soup = BeautifulSoup(content_html, 'lxml')
                detail["full_content"] = content_soup.get_text(separator='\n', strip=True)
                detail["word_count"] = detail_data.get('wordCount', 0)
                detail["read_time"] = detail_data.get('readTime', 0)

            # 互动数据
            external_data = detail_data.get('externalData', {})
            if isinstance(external_data, dict):
                detail["comment_count_actual"] = external_data.get('commentCount', 0)
                detail["digg_count"] = external_data.get('diggCount', 0)

            # 如果 __INITIAL_STATE__ 无内容，降级到 HTML 解析
            if not detail["full_content"]:
                soup = BeautifulSoup(resp.text, 'lxml')
                content_selectors = ['.md_preview', '.user-article', '.main-content']
                for sel in content_selectors:
                    content_div = soup.select_one(sel)
                    if content_div:
                        for tag in content_div.select('script, style, iframe'):
                            tag.decompose()
                        detail["full_content"] = content_div.get_text(separator='\n', strip=True)
                        if len(detail["full_content"]) > 50:
                            break

            # 评论需登录才能查看内容，仅记录数量
            if detail["comment_count_actual"] == 0:
                comment_el = resp.text
                import re
                cm_match = re.search(r'class="comment-num"[^>]*>(\d+)', comment_el)
                if cm_match:
                    detail["comment_count_actual"] = int(cm_match.group(1))

        except Exception as e:
            print(f"    [详情解析错误] {url}: {e}")

        completed.add(url)
        self.state["completed_detail_urls"] = list(completed)
        save_state(self.state)

        return detail

    def crawl_details(self, articles: List[dict], max_workers: int = MAX_WORKERS) -> List[dict]:
        """并发爬取文章详情"""
        if not articles:
            return []

        ensure_json_dir()
        details = []
        completed = set(self.state.get("completed_detail_urls", []))
        to_fetch = [a for a in articles if a.get("url") and a["url"] not in completed]

        print(f"[详情爬取] 共 {len(articles)} 条, 待爬取 {len(to_fetch)} 条")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch_detail, art): art for art in to_fetch}
            done_count = 0
            for future in as_completed(futures):
                detail = future.result()
                if detail:
                    details.append(detail)
                    # 保存为 JSON
                    article_id = detail.get("article_id", "") or hashlib.md5(detail["url"].encode()).hexdigest()[:12]
                    json_path = JSON_DIR / f"csdn_{article_id}.json"
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(detail, f, ensure_ascii=False, indent=2)
                done_count += 1
                if done_count % 5 == 0:
                    print(f"  [详情] {done_count}/{len(to_fetch)}")

        print(f"[详情爬取] 完成，获取 {len(details)} 条详情")
        return details


# ============================================================================
# CSV 输出
# ============================================================================

def save_to_csv(articles: List[dict], filepath: Path, mode: str = 'a'):
    """保存文章列表到 CSV，追加模式"""
    if not articles:
        return

    # 统一字段
    fieldnames = [
        'source', 'phase', 'keyword', 'article_id', 'title',
        'description', 'url', 'content_url',
        'author_name', 'author_id', 'author', 'nickname',
        'created_at', 'timestamp',
        'click_count', 'stars', 'digg', 'view', 'collections', 'comment_count',
        'tags', 'language', 'score', 'type',
        'is_pgc', 'is_course', 'is_top',
        'domains', 'subjects',
        'keyword_matched',
    ]

    file_exists = filepath.exists()
    with open(filepath, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists or mode == 'w':
            writer.writeheader()
        for art in articles:
            row = {k: art.get(k, "") for k in fieldnames}
            writer.writerow(row)

    print(f"[CSV] 已保存 {len(articles)} 条到 {filepath}")


# ============================================================================
# 主控
# ============================================================================

def main():
    print("=" * 60)
    print("魔搭社区 (ModelScope) 爬虫")
    print("研究主题: AI编程对程序员工作的影响")
    print("=" * 60)

    state = load_state()
    session = requests.Session()
    session.headers.update(HEADERS)

    all_articles = []

    # ---- Source A: 研习社 ----
    print("\n" + "=" * 60)
    print("【Source A】研习社 (modelscope.cn/learn)")
    print("=" * 60)
    crawler_a = LearnCrawler(session, state)
    articles_a = crawler_a.crawl()  # 采集全部275篇
    if articles_a:
        save_to_csv(articles_a, CSV_FILE, mode='a')
        all_articles.extend(articles_a)

    # ---- Source B: CSDN社区 ----
    print("\n" + "=" * 60)
    print("【Source B】CSDN社区 (modelscope.csdn.net)")
    print("=" * 60)
    crawler_b = CSDNCommunityCrawler(session, state)
    articles_b = crawler_b.crawl_list()

    if articles_b:
        save_to_csv(articles_b, CSV_FILE, mode='a')
        all_articles.extend(articles_b)

    # --- Source B: 爬取详情 ---
    if articles_b:
        print("\n" + "=" * 60)
        print("【Source B】爬取详情页 (全文 + 评论)")
        print("=" * 60)
        details = crawler_b.crawl_details(articles_b)

    # ---- 统计 ----
    print("\n" + "=" * 60)
    print("爬取完成")
    print("=" * 60)
    print(f"  研习社文章:     {len(articles_a)} 条")
    print(f"  CSDN社区文章:  {len(articles_b)} 条")
    print(f"  CSDN详情页:     {len(details) if articles_b else 0} 条")
    print(f"  总文章数:       {len(all_articles)} 条")
    print(f"  CSV文件:        {CSV_FILE}")
    print(f"  JSON详情目录:   {JSON_DIR}/")

    if articles_b and details:
        state["completed_detail_urls"] = list(
            set(state.get("completed_detail_urls", []))
        )
        save_state(state)

    session.close()


if __name__ == "__main__":
    main()
