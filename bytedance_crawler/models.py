"""数据模型 — 定义每条岗位记录的结构."""

from __future__ import annotations

from pydantic import BaseModel


class Metadata(BaseModel):
    """爬取元信息."""
    platform: str
    track: str                          # experienced / campus / intern
    crawl_timestamp: str                # ISO-8601
    job_id: str
    url: str


class BasicInfo(BaseModel):
    """岗位基本信息."""
    job_title: str
    sub_title: str | None = None
    category_path: list[str] = []       # e.g. ["研发", "后端"]
    category_en_path: list[str] = []    # e.g. ["R&D", "Backend"]
    location: list[str] = []            # e.g. ["北京", "上海"]
    publish_date: str | None = None     # YYYY-MM-DD


class Requirements(BaseModel):
    """职位描述与任职要求."""
    description: str = ""
    requirement: str = ""
    raw_jd_text: str = ""               # description + requirement 合并文本


class JobRecord(BaseModel):
    """一条完整的岗位记录."""
    metadata: Metadata
    basic_info: BasicInfo
    requirements: Requirements
