"""SQLite 持久化存储 — 去重 & 断点续爬."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Storage:
    """轻量 SQLite 存储：去重、断点续爬."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                platform TEXT NOT NULL,
                track    TEXT NOT NULL,
                job_id   TEXT NOT NULL,
                url      TEXT NOT NULL DEFAULT '',
                payload  TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                PRIMARY KEY (platform, track, job_id)
            );
        """)
        self._conn.commit()

    def has(self, platform: str, track: str, job_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM jobs WHERE platform=? AND track=? AND job_id=? LIMIT 1",
            (platform, track, job_id),
        ).fetchone()
        return row is not None

    def save(self, platform: str, track: str, job_id: str, url: str, payload: dict[str, Any]) -> None:
        payload_json = json.dumps(payload, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            INSERT INTO jobs(platform, track, job_id, url, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, track, job_id) DO UPDATE SET
                url=excluded.url, payload=excluded.payload
        """, (platform, track, job_id, url, payload_json, now))
        self._conn.commit()

    def count(self, platform: str, track: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE platform=? AND track=?",
            (platform, track),
        ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._conn.close()
