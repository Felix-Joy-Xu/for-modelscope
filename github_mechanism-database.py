"""
SQLite 数据库 — 机制化编码存储
按 M1–M4 + H1–H3 对应表设计 schema
"""

import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """获取数据库连接。"""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database(db_path: str = None):
    """初始化数据库 schema。"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # ---- 元数据表 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repos (
            repo_id         TEXT PRIMARY KEY,       -- "owner/repo"
            full_name       TEXT,
            description     TEXT,
            stars           INTEGER,
            forks           INTEGER,
            language        TEXT,
            org_type        TEXT,                    -- 大厂平台/中型互联网/AI原生
            ai_adoption_date TEXT,                   -- AI 工具引入时间
            created_at      TEXT,
            updated_at      TEXT,
            collected_at    TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id         TEXT,
            username        TEXT,
            contributions   INTEGER,                -- 在该仓库的 commit 数
            is_bot          INTEGER DEFAULT 0,       -- 是否为 bot
            collected_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(repo_id, username)
        )
    """)

    # ---- M1: PR 生命周期（注意力迁移指标） ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS m1_pr_lifecycle (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id         TEXT NOT NULL,
            pr_number       INTEGER NOT NULL,
            title           TEXT,
            state           TEXT,                    -- open/closed/merged
            author          TEXT,
            author_is_bot   INTEGER DEFAULT 0,

            -- 时间指标
            created_at      TEXT,
            merged_at       TEXT,
            closed_at       TEXT,
            cycle_hours     REAL,                    -- 从创建到合并的小时数

            -- 审查负担指标
            review_comments INTEGER DEFAULT 0,       -- review comment 总数
            general_comments INTEGER DEFAULT 0,      -- 一般评论数
            review_rounds   INTEGER DEFAULT 0,       -- review 轮次数
            changes_requested INTEGER DEFAULT 0,     -- "CHANGES_REQUESTED" 次数
            approvals       INTEGER DEFAULT 0,       -- "APPROVED" 次数
            unique_reviewers INTEGER DEFAULT 0,      -- 参与 review 的独立人数
            commits_count   INTEGER DEFAULT 0,       -- PR 内的 commit 数

            -- AI 标记
            has_ai_label    INTEGER DEFAULT 0,        -- 是否有 AI 相关标签
            has_ai_keyword  INTEGER DEFAULT 0,        -- 标题/描述是否含 AI 关键词
            ai_signals      TEXT,                     -- JSON: 匹配到的具体信号

            -- 代码规模
            additions       INTEGER DEFAULT 0,
            deletions       INTEGER DEFAULT 0,
            changed_files   INTEGER DEFAULT 0,

            -- 时间分期
            period          TEXT,                     -- "pre_ai" / "post_ai"

            collected_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(repo_id, pr_number)
        )
    """)

    # ---- M3: 过程可见性（bot 与管理介入） ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS m3_pr_visibility (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id         TEXT NOT NULL,
            pr_number       INTEGER NOT NULL,

            -- bot 与自动化
            bot_comments    INTEGER DEFAULT 0,        -- bot 发出的评论数
            bot_reviews     INTEGER DEFAULT 0,        -- bot 发出的 review 数
            automated_checks INTEGER DEFAULT 0,       -- CI/CD 自动检查数
            bot_usernames   TEXT,                      -- JSON: 参与的 bot 列表

            -- 管理/合规介入
            visibility_keywords_count INTEGER DEFAULT 0,
            visibility_keywords_found TEXT,            -- JSON: 匹配到的关键词

            -- 时间分期
            period          TEXT,

            collected_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(repo_id, pr_number)
        )
    """)

    # ---- M4: 问责—权力鸿沟（话语编码） ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS m4_issue_discourse (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id         TEXT NOT NULL,
            issue_number    INTEGER NOT NULL,
            title           TEXT,
            state           TEXT,
            author          TEXT,
            is_bug          INTEGER DEFAULT 0,        -- 是否为 bug 类 issue
            labels          TEXT,                      -- JSON: 标签列表

            created_at      TEXT,
            closed_at       TEXT,
            comments_count  INTEGER DEFAULT 0,

            -- 话语编码计数
            individual_blame_count  INTEGER DEFAULT 0,
            ai_attribution_count    INTEGER DEFAULT 0,
            systemic_attribution_count INTEGER DEFAULT 0,
            accountability_gap_count INTEGER DEFAULT 0,

            -- 匹配的具体话语片段
            discourse_matches TEXT,                    -- JSON: {类别: [匹配片段]}

            -- 参与者博弈
            unique_commenters       INTEGER DEFAULT 0,
            committer_vs_reviewer   TEXT,              -- JSON: 角色话语分布

            -- 时间分期
            period          TEXT,

            collected_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(repo_id, issue_number)
        )
    """)

    # ---- M4: 话语片段明细（用于定性分析） ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS m4_discourse_snippets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id         TEXT NOT NULL,
            issue_number    INTEGER NOT NULL,
            comment_id      INTEGER,
            author          TEXT,
            created_at      TEXT,
            discourse_type  TEXT,                      -- individual_blame/ai_attribution/...
            matched_keyword TEXT,                      -- 匹配的关键词
            context_text    TEXT,                      -- 包含关键词的上下文文本（前后各100字符）
            full_comment    TEXT                       -- 完整评论文本
        )
    """)

    # ---- M2: 贡献者跨仓库流动性 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS m2_contributor_mobility (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT NOT NULL,
            home_repo_id    TEXT NOT NULL,             -- 主仓库（企业AI深度集成仓库）
            home_contributions INTEGER,

            -- 外部活动统计
            external_repos_count    INTEGER DEFAULT 0, -- 在外部仓库的活跃数
            external_commits_count  INTEGER DEFAULT 0, -- 外部 commit/push 事件数
            external_prs_count      INTEGER DEFAULT 0, -- 外部 PR 事件数
            external_issues_count   INTEGER DEFAULT 0, -- 外部 issue 事件数
            external_repos_list     TEXT,               -- JSON: 外部活跃仓库列表

            -- 时间段
            observation_period      TEXT,               -- "pre_ai" / "post_ai"
            period_start            TEXT,
            period_end              TEXT,

            collected_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(username, home_repo_id, observation_period)
        )
    """)

    # ---- 采集日志 ----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id         TEXT,
            mechanism       TEXT,                      -- M1/M2/M3/M4
            action          TEXT,                      -- start/complete/error
            items_collected INTEGER DEFAULT 0,
            message         TEXT,
            timestamp       TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    logger.info(f"数据库初始化完成: {db_path or DB_PATH}")


class MechanismDB:
    """机制化数据的存取接口。"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        init_database(self.db_path)
        self.conn = get_connection(self.db_path)

    def close(self):
        self.conn.close()

    # ---- 仓库元数据 ----

    def upsert_repo(self, repo_id: str, data: dict):
        self.conn.execute("""
            INSERT INTO repos (repo_id, full_name, description, stars, forks,
                               language, org_type, ai_adoption_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                stars=excluded.stars, forks=excluded.forks,
                updated_at=excluded.updated_at, collected_at=datetime('now')
        """, (
            repo_id, data.get("full_name"), data.get("description"),
            data.get("stargazers_count"), data.get("forks_count"),
            data.get("language"), data.get("org_type"),
            data.get("ai_adoption_date"),
            data.get("created_at"), data.get("updated_at"),
        ))
        self.conn.commit()

    # ---- M1: PR 生命周期 ----

    def insert_pr_lifecycle(self, record: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO m1_pr_lifecycle (
                repo_id, pr_number, title, state, author, author_is_bot,
                created_at, merged_at, closed_at, cycle_hours,
                review_comments, general_comments, review_rounds,
                changes_requested, approvals, unique_reviewers, commits_count,
                has_ai_label, has_ai_keyword, ai_signals,
                additions, deletions, changed_files, period
            ) VALUES (
                :repo_id, :pr_number, :title, :state, :author, :author_is_bot,
                :created_at, :merged_at, :closed_at, :cycle_hours,
                :review_comments, :general_comments, :review_rounds,
                :changes_requested, :approvals, :unique_reviewers, :commits_count,
                :has_ai_label, :has_ai_keyword, :ai_signals,
                :additions, :deletions, :changed_files, :period
            )
        """, record)
        self.conn.commit()

    def batch_insert_pr_lifecycle(self, records: List[dict]):
        self.conn.executemany("""
            INSERT OR REPLACE INTO m1_pr_lifecycle (
                repo_id, pr_number, title, state, author, author_is_bot,
                created_at, merged_at, closed_at, cycle_hours,
                review_comments, general_comments, review_rounds,
                changes_requested, approvals, unique_reviewers, commits_count,
                has_ai_label, has_ai_keyword, ai_signals,
                additions, deletions, changed_files, period
            ) VALUES (
                :repo_id, :pr_number, :title, :state, :author, :author_is_bot,
                :created_at, :merged_at, :closed_at, :cycle_hours,
                :review_comments, :general_comments, :review_rounds,
                :changes_requested, :approvals, :unique_reviewers, :commits_count,
                :has_ai_label, :has_ai_keyword, :ai_signals,
                :additions, :deletions, :changed_files, :period
            )
        """, records)
        self.conn.commit()

    # ---- M3: 过程可见性 ----

    def insert_pr_visibility(self, record: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO m3_pr_visibility (
                repo_id, pr_number,
                bot_comments, bot_reviews, automated_checks, bot_usernames,
                visibility_keywords_count, visibility_keywords_found, period
            ) VALUES (
                :repo_id, :pr_number,
                :bot_comments, :bot_reviews, :automated_checks, :bot_usernames,
                :visibility_keywords_count, :visibility_keywords_found, :period
            )
        """, record)
        self.conn.commit()

    # ---- M4: 问责话语 ----

    def insert_issue_discourse(self, record: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO m4_issue_discourse (
                repo_id, issue_number, title, state, author, is_bug, labels,
                created_at, closed_at, comments_count,
                individual_blame_count, ai_attribution_count,
                systemic_attribution_count, accountability_gap_count,
                discourse_matches, unique_commenters, committer_vs_reviewer,
                period
            ) VALUES (
                :repo_id, :issue_number, :title, :state, :author, :is_bug, :labels,
                :created_at, :closed_at, :comments_count,
                :individual_blame_count, :ai_attribution_count,
                :systemic_attribution_count, :accountability_gap_count,
                :discourse_matches, :unique_commenters, :committer_vs_reviewer,
                :period
            )
        """, record)
        self.conn.commit()

    def insert_discourse_snippet(self, record: dict):
        self.conn.execute("""
            INSERT INTO m4_discourse_snippets (
                repo_id, issue_number, comment_id, author, created_at,
                discourse_type, matched_keyword, context_text, full_comment
            ) VALUES (
                :repo_id, :issue_number, :comment_id, :author, :created_at,
                :discourse_type, :matched_keyword, :context_text, :full_comment
            )
        """, record)
        self.conn.commit()

    # ---- M2: 贡献者流动性 ----

    def upsert_contributor(self, repo_id: str, username: str,
                           contributions: int, is_bot: bool = False):
        self.conn.execute("""
            INSERT INTO contributors (repo_id, username, contributions, is_bot)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(repo_id, username) DO UPDATE SET
                contributions=excluded.contributions,
                is_bot=excluded.is_bot,
                collected_at=datetime('now')
        """, (repo_id, username, contributions, int(is_bot)))
        self.conn.commit()

    def insert_contributor_mobility(self, record: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO m2_contributor_mobility (
                username, home_repo_id, home_contributions,
                external_repos_count, external_commits_count,
                external_prs_count, external_issues_count,
                external_repos_list, observation_period,
                period_start, period_end
            ) VALUES (
                :username, :home_repo_id, :home_contributions,
                :external_repos_count, :external_commits_count,
                :external_prs_count, :external_issues_count,
                :external_repos_list, :observation_period,
                :period_start, :period_end
            )
        """, record)
        self.conn.commit()

    # ---- 日志 ----

    def log(self, repo_id: str, mechanism: str, action: str,
            items: int = 0, message: str = ""):
        self.conn.execute("""
            INSERT INTO collection_log (repo_id, mechanism, action, items_collected, message)
            VALUES (?, ?, ?, ?, ?)
        """, (repo_id, mechanism, action, items, message))
        self.conn.commit()

    # ---- 查询 ----

    def get_pr_count(self, repo_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM m1_pr_lifecycle WHERE repo_id=?", (repo_id,)
        ).fetchone()
        return row[0] if row else 0

    def get_issue_count(self, repo_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM m4_issue_discourse WHERE repo_id=?", (repo_id,)
        ).fetchone()
        return row[0] if row else 0

    def query(self, sql: str, params: tuple = ()) -> list:
        """执行任意查询，返回字典列表。"""
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
