#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Discussions 爬取 - 混合策略
先用 REST API 搜索热门仓库，再爬取这些仓库的 Discussions
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
        logging.FileHandler("crawler_discussions.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 已知有活跃 Discussions 的 AI/编程相关仓库
REPOS_WITH_DISCUSSIONS = [
    "github/feedback",           # GitHub 官方反馈
    "orgs/community",            # GitHub 社区
    "microsoft/vscode",          # VS Code
    "microsoft/vscode-copilot",  # Copilot
    "github/copilot",            # GitHub Copilot
    "openai/openai-cookbook",    # OpenAI
    "getcursor/cursor",          # Cursor
    "langgenius/dify",           # Dify (AI 应用)
    "n8n-io/n8n",                # n8n (自动化)
    "lobechat/lobechat",         # Lobe Chat
    "continuedev/continue",      # Continue (AI 编程助手)
    "sourcegraph/cody",          # Cody (AI 编程助手)
    "tabnine/tabnine-vscode",    # Tabnine
    "amazonwebservices/amazon-q-developer",  # Amazon Q
    "codeium/codeium",           # Codeium
    "zed-industries/zed",        # Zed 编辑器
    "astral-sh/ruff",            # Ruff (Python linter)
    "denoland/deno",             # Deno
    "vercel/next.js",            # Next.js
    "tailwindlabs/tailwindcss",  # Tailwind CSS
    "shadcn-ui/ui",              # shadcn/ui
    "angular/angular",           # Angular
    "facebook/react",            # React
    "vuejs/core",                # Vue
    "sveltejs/svelte",           # Svelte
    "rust-lang/rust",            # Rust
    "python/cpython",            # Python
    "golang/go",                 # Go
    "nodejs/node",               # Node.js
    "typescript/typescript",     # TypeScript
    "godotengine/godot",         # Godot 引擎
    "flutter/flutter",           # Flutter
    "pytorch/pytorch",           # PyTorch
    "tensorflow/tensorflow",     # TensorFlow
    "kubernetes/kubernetes",     # Kubernetes
    "docker/compose",            # Docker
    "hashicorp/terraform",       # Terraform
    "ansible/ansible",           # Ansible
    "apache/spark",              # Spark
    "apache/kafka",              # Kafka
    "elastic/elasticsearch",     # Elasticsearch
    "grafana/grafana",           # Grafana
    "prometheus/prometheus",     # Prometheus
    "neovim/neovim",             # Neovim
    "helix-editor/helix",        # Helix 编辑器
    "lapce/lapce",               # Lapce 编辑器
    "oven-sh/bun",               # Bun
    "swiftlang/swift",           # Swift
    "kotlin/kotlin-spec",        # Kotlin
    "dotnet/aspnetcore",         # .NET
    "spring-projects/spring-framework",  # Spring
    "rails/rails",               # Rails
    "django/django",             # Django
    "fastapi/fastapi",           # FastAPI
    "gin-gonic/gin",             # Gin
    "expressjs/express",         # Express
    "nestjs/nest",               # NestJS
    "supabase/supabase",         # Supabase
    "prisma/prisma",             # Prisma
    "hasura/graphql-engine",     # Hasura
    "apollographql/apollo-client",  # Apollo
    "graphql/graphql-js",        # GraphQL
    "reduxjs/redux",             # Redux
    "mobxjs/mobx",               # MobX
    "solidjs/solid",             # SolidJS
    "preactjs/preact",           # Preact
    "emscripten-core/emscripten",  # Emscripten
    "webpack/webpack",           # Webpack
    "vitejs/vite",               # Vite
    "rollup/rollup",             # Rollup
    "esbuild/esbuild",           # esbuild
    "parcel-bundler/parcel",     # Parcel
    "babel/babel",               # Babel
    "postcss/postcss",           # PostCSS
    "lodash/lodash",             # Lodash
    "moment/moment",             # Moment
    "date-fns/date-fns",         # date-fns
    "immerjs/immer",             # Immer
    "zod/zod",                   # Zod
    "tanstack/query",            # TanStack Query
    "pmndrs/zustand",            # Zustand
    "jotai-labs/jotai",          # Jotai
    "valibot/valibot",           # Valibot
    "biomejs/biome",             # Biome
    "oxc-project/oxc",           # Oxc
    "rolldown/rolldown",         # Rolldown
    "turborepo/turborepo",       # Turborepo
    "nx/nx",                     # Nx
    "pnpm/pnpm",                 # pnpm
    "yarnpkg/berry",             # Yarn Berry
    "npm/cli",                   # npm CLI
    "oven-sh/bun",               # Bun
    "denoland/deno",             # Deno
    "nodejs/node",               # Node.js
    "bunnyway/bolt",             # Bolt
    "stackblitz/bolt.new",       # Bolt.new
    "lovable-ai/lovable",        # Lovable
    "windsurf-ai/windsurf",      # Windsurf
    "devin-ai/devin",            # Devin
    "cursor-ai/cursor",          # Cursor AI
    "anthropics/anthropic-cookbook",  # Anthropic
    "google-gemini/gemini-api",  # Gemini
    "mistralai/mistral",         # Mistral
    "cohere-ai/cohere",          # Cohere
    "stability-ai/stablediffusion",  # Stable Diffusion
    "huggingface/transformers",  # Hugging Face
    "ggerganov/llama.cpp",       # llama.cpp
    "ollama/ollama",             # Ollama
    "lm-sys/FastChat",           # FastChat
    "vllm-project/vllm",         # vLLM
    "langchain-ai/langchain",    # LangChain
    "run-llama/llama_index",     # LlamaIndex
    "crewAIInc/crewAI",          # CrewAI
    "microsoft/autogen",         # AutoGen
    "comfyanonymous/ComfyUI",    # ComfyUI
    "AUTOMATIC1111/stable-diffusion-webui",  # SD WebUI
    "invoke-ai/InvokeAI",        # InvokeAI
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

    def get_stats(self) -> Dict:
        pipeline = [
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        return {item["_id"]: item["count"] for item in self.collection.aggregate(pipeline)}

    def close(self):
        self.client.close()


class GitHubDiscussionCrawler:
    """
    通过 REST API 爬取指定仓库的 Discussions
    GitHub REST API: GET /repos/{owner}/{repo}/discussions
    """
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
                    logger.warning(f"[REST] Rate limited, waiting 60s...")
                    time.sleep(60)
                    self._rotate_token()
                    continue
                if resp.status_code == 404:
                    logger.warning(f"[REST] 404: {url}")
                    return None
                if resp.status_code == 410:
                    logger.warning(f"[REST] 410 Gone: {url} (Discussions not enabled)")
                    return None
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

    def _request_list(self, url: str, params: Optional[Dict] = None) -> Optional[List]:
        """返回列表结果的请求"""
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
                    return None
                if resp.status_code == 403:
                    logger.warning(f"[REST] Rate limited, waiting 60s...")
                    time.sleep(60)
                    self._rotate_token()
                    continue
                if resp.status_code in (404, 410):
                    return None
                if resp.status_code in (502, 503, 504):
                    wait = min(30 * (attempt + 1), 120)
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

    def crawl_repo_discussions(self, repo: str, phase: str) -> int:
        """
        爬取单个仓库的所有 Discussions
        REST API: GET /repos/{owner}/{repo}/discussions
        """
        # 先检查仓库是否存在且 Discussions 已启用
        check_url = f"https://api.github.com/repos/{repo}"
        check = self._request(check_url)
        if not check:
            logger.warning(f"[REST] Repo {repo} not accessible")
            return 0

        # 检查是否有 discussions 功能
        has_discussions = check.get("has_discussions", False)
        if not has_discussions:
            logger.info(f"[REST] {repo} has no discussions enabled")
            return 0

        logger.info(f"[REST] {repo} has discussions! Crawling...")

        total = 0
        page = 1
        max_pages = 20  # 最多 20 页

        while page <= max_pages:
            url = f"https://api.github.com/repos/{repo}/discussions"
            params = {
                "per_page": 100,
                "page": page,
                "direction": "desc",
                "sort": "created"
            }

            discussions = self._request_list(url, params)
            if not discussions or len(discussions) == 0:
                break

            for d in discussions:
                created_at = d.get("created_at", "")
                # 判断属于哪个 phase
                if created_at < PHASE_A_START or created_at > PHASE_B_END:
                    continue
                doc_phase = phase
                if created_at <= PHASE_A_END:
                    doc_phase = "A"
                else:
                    doc_phase = "B"

                discussion_doc = {
                    "source": "github_discussion",
                    "phase": doc_phase,
                    "lang": "en",
                    "url": d.get("html_url", ""),
                    "title": d.get("title", ""),
                    "text": d.get("body", "") or "",
                    "created_at": created_at,
                    "author": d.get("user", {}).get("login") if d.get("user") else None,
                    "metadata": {
                        "repo": repo,
                        "search_keyword": repo,
                        "comments_count": d.get("comments", 0),
                        "category": d.get("category", {}).get("name", "") if d.get("category") else ""
                    }
                }
                self.db.insert(discussion_doc)
                total += 1

                # 爬取评论
                comments_url = d.get("comments_url", "")
                if comments_url and d.get("comments", 0) > 0:
                    self._crawl_comments(comments_url, d.get("html_url", ""),
                                         d.get("node_id", ""), doc_phase, repo)

            logger.info(f"[REST] {repo} page {page}: {len(discussions)} discussions, total={total}")
            page += 1
            time.sleep(random.uniform(1, 2))

        logger.info(f"[REST] Finished {repo}: {total} discussions")
        return total

    def _crawl_comments(self, comments_url: str, discussion_url: str,
                        discussion_node_id: str, phase: str, repo: str):
        """爬取 Discussion 的评论"""
        page = 1
        total = 0
        max_pages = 5

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
                        "lang": "en",
                        "url": c.get("html_url", discussion_url),
                        "title": "",
                        "text": c.get("body", "") or "",
                        "created_at": c.get("created_at", ""),
                        "author": c.get("user", {}).get("login") if c.get("user") else None,
                        "metadata": {
                            "repo": repo,
                            "parent_type": "discussion",
                            "parent_id": discussion_node_id,
                            "search_keyword": repo
                        }
                    }
                    self.db.insert(comment_doc)
                    total += 1

                page += 1
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"[REST] Comment error: {e}")
                break


def main():
    logger.info("=" * 60)
    logger.info("GitHub Discussions Crawl (Repo-based REST API)")
    logger.info("=" * 60)

    db = DB(MONGO_URI, DB_NAME)
    crawler = GitHubDiscussionCrawler(TOKENS, db)

    total = 0
    for i, repo in enumerate(REPOS_WITH_DISCUSSIONS):
        logger.info(f"[{i+1}/{len(REPOS_WITH_DISCUSSIONS)}] Checking {repo}...")
        time.sleep(random.uniform(1, 3))
        count = crawler.crawl_repo_discussions(repo, "B")
        total += count

    stats = db.get_stats()
    logger.info("=" * 60)
    logger.info(f"Discussions crawl complete: total={total}")
    logger.info(f"DB stats: {stats}")
    logger.info("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
