"""
GitHub API 客户端
带限速、分页、重试和认证管理
"""

import time
import requests
import logging
from typing import Optional, Generator
from config import (
    GITHUB_TOKEN, API_BASE, REQUESTS_PER_SECOND,
    MAX_RETRIES, PER_PAGE,
)

logger = logging.getLogger(__name__)


class GitHubClient:
    """封装 GitHub REST API 的客户端，自动处理限速、分页和重试。"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or GITHUB_TOKEN
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            })
        else:
            self.session.headers.update({
                "Accept": "application/vnd.github+json",
            })
            logger.warning(
                "未设置 GITHUB_TOKEN，将使用未认证模式（限 60 请求/小时）。"
                "请设置环境变量 GITHUB_TOKEN 以获得 5000 请求/小时的配额。"
            )
        self._last_request_time = 0.0
        self._request_count = 0
        self._min_interval = 1.0 / REQUESTS_PER_SECOND

    # ---- 核心请求方法 ----

    def _throttle(self):
        """限速：确保请求间隔不低于设定值。"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

    def _handle_rate_limit(self, response: requests.Response):
        """处理 GitHub API 限速响应（403 + rate limit header）。"""
        remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
        reset_ts = response.headers.get("X-RateLimit-Reset")

        if response.status_code == 403 and reset_ts:
            wait_seconds = max(int(reset_ts) - int(time.time()), 1) + 5
            logger.warning(
                f"触发 GitHub 限速，剩余配额: {remaining}，"
                f"等待 {wait_seconds} 秒后重试..."
            )
            time.sleep(wait_seconds)
            return True  # 需要重试
        return False

    def get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """发送 GET 请求，自动限速和重试。"""
        url = f"{API_BASE}{endpoint}" if endpoint.startswith("/") else endpoint
        params = params or {}

        for attempt in range(MAX_RETRIES):
            self._throttle()
            self._last_request_time = time.time()
            self._request_count += 1

            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 200:
                    return resp.json()

                if self._handle_rate_limit(resp):
                    continue  # 限速后重试

                if resp.status_code == 404:
                    logger.debug(f"资源不存在: {url}")
                    return None

                if resp.status_code in (502, 503):
                    wait = 2 ** attempt * 5
                    logger.warning(f"服务器错误 {resp.status_code}，{wait}s 后重试")
                    time.sleep(wait)
                    continue

                logger.error(
                    f"请求失败 [{resp.status_code}]: {url}\n"
                    f"响应: {resp.text[:500]}"
                )
                return None

            except requests.exceptions.RequestException as e:
                wait = 2 ** attempt * 3
                logger.warning(f"网络异常: {e}，{wait}s 后重试 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)

        logger.error(f"请求 {url} 在 {MAX_RETRIES} 次重试后仍失败")
        return None

    def get_paginated(
        self, endpoint: str, params: dict = None, max_items: int = None
    ) -> Generator[dict, None, None]:
        """
        自动分页获取所有结果的生成器。

        Args:
            endpoint: API 端点
            params: 查询参数
            max_items: 最多返回的条目数
        Yields:
            每个结果项（dict）
        """
        params = params or {}
        params["per_page"] = PER_PAGE
        page = 1
        total_yielded = 0

        while True:
            params["page"] = page
            data = self.get(endpoint, params)

            if not data or (isinstance(data, list) and len(data) == 0):
                break

            items = data if isinstance(data, list) else data.get("items", [])
            if not items:
                break

            for item in items:
                yield item
                total_yielded += 1
                if max_items and total_yielded >= max_items:
                    return

            if len(items) < PER_PAGE:
                break  # 最后一页

            page += 1

    # ---- 便捷方法 ----

    def get_repo_info(self, owner: str, repo: str) -> Optional[dict]:
        """获取仓库基本信息。"""
        return self.get(f"/repos/{owner}/{repo}")

    def get_pulls(
        self, owner: str, repo: str,
        state: str = "all", sort: str = "created",
        direction: str = "desc", max_items: int = None,
    ) -> Generator[dict, None, None]:
        """获取 Pull Requests。"""
        params = {"state": state, "sort": sort, "direction": direction}
        yield from self.get_paginated(
            f"/repos/{owner}/{repo}/pulls", params, max_items
        )

    def get_pull_reviews(
        self, owner: str, repo: str, pull_number: int
    ) -> list:
        """获取某个 PR 的所有 review。"""
        reviews = list(self.get_paginated(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        ))
        return reviews

    def get_pull_comments(
        self, owner: str, repo: str, pull_number: int
    ) -> list:
        """获取某个 PR 的所有行内评论（review comments）。"""
        comments = list(self.get_paginated(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/comments"
        ))
        return comments

    def get_pull_commits(
        self, owner: str, repo: str, pull_number: int
    ) -> list:
        """获取某个 PR 的所有 commit。"""
        commits = list(self.get_paginated(
            f"/repos/{owner}/{repo}/pulls/{pull_number}/commits"
        ))
        return commits

    def get_issues(
        self, owner: str, repo: str,
        state: str = "all", labels: str = "",
        sort: str = "created", direction: str = "desc",
        max_items: int = None,
    ) -> Generator[dict, None, None]:
        """获取 Issues（排除 PR）。"""
        params = {
            "state": state, "sort": sort, "direction": direction,
        }
        if labels:
            params["labels"] = labels

        for item in self.get_paginated(
            f"/repos/{owner}/{repo}/issues", params, max_items
        ):
            # GitHub Issues API 会把 PR 也返回，需要过滤
            if "pull_request" not in item:
                yield item

    def get_issue_comments(
        self, owner: str, repo: str, issue_number: int
    ) -> list:
        """获取某个 Issue 的所有评论。"""
        comments = list(self.get_paginated(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
        ))
        return comments

    def get_contributors(
        self, owner: str, repo: str, max_items: int = None
    ) -> Generator[dict, None, None]:
        """获取仓库贡献者列表（按 commit 数排序）。"""
        yield from self.get_paginated(
            f"/repos/{owner}/{repo}/contributors", max_items=max_items
        )

    def get_user_events(
        self, username: str, max_items: int = 300
    ) -> Generator[dict, None, None]:
        """获取用户的公开事件（最近 90 天，最多 300 条）。"""
        yield from self.get_paginated(
            f"/users/{username}/events/public", max_items=max_items
        )

    def search_issues(
        self, query: str, sort: str = "created",
        order: str = "desc", max_items: int = None,
    ) -> Generator[dict, None, None]:
        """搜索 Issues/PR。"""
        params = {"q": query, "sort": sort, "order": order}
        for item in self.get_paginated(
            "/search/issues", params, max_items
        ):
            yield item

    @property
    def request_count(self) -> int:
        """已发送的请求总数。"""
        return self._request_count

    def check_rate_limit(self) -> dict:
        """检查当前 API 配额状态。"""
        data = self.get("/rate_limit")
        if data:
            core = data.get("resources", {}).get("core", {})
            search = data.get("resources", {}).get("search", {})
            logger.info(
                f"API 配额 — Core: {core.get('remaining')}/{core.get('limit')} "
                f"(重置于 {time.ctime(core.get('reset', 0))}), "
                f"Search: {search.get('remaining')}/{search.get('limit')}"
            )
            return data
        return {}
