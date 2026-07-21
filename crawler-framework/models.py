from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Platform = Literal["bytedance", "tencent", "alibaba", "meituan"]
Track = Literal["experienced", "campus", "intern"]


class Metadata(BaseModel):
    platform: Platform
    crawl_timestamp: datetime
    job_id: str = Field(min_length=1)
    track: Track | None = None


class BasicInfo(BaseModel):
    job_title: str = Field(min_length=1)
    category_path: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    publish_date: str | None = None


class Requirements(BaseModel):
    education_level: str | None = None
    experience_years: str | None = None
    raw_jd_text: str = Field(default="")


class JobRecord(BaseModel):
    metadata: Metadata
    basic_info: BasicInfo
    requirements: Requirements

