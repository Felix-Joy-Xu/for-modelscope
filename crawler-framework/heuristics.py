from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _iter_nodes(obj: Any) -> Iterable[Any]:
    stack = [obj]
    while stack:
        cur = stack.pop()
        yield cur
        if isinstance(cur, dict):
            for v in cur.values():
                stack.append(v)
        elif isinstance(cur, list):
            for v in cur:
                stack.append(v)


def _get_str(d: dict[str, Any], keys: list[str]) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and str(v).strip():
            return str(v)
    return None


def _get_list_str(d: dict[str, Any], keys: list[str]) -> list[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            out: list[str] = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
            if out:
                return out
        if isinstance(v, str) and v.strip():
            # 有些站点用 "北京/上海" 之类
            parts = [p.strip() for p in v.replace("|", "/").split("/") if p.strip()]
            if parts:
                return parts
    return []


def extract_job_like_dicts(payload: Any) -> list[dict[str, Any]]:
    """
    从未知 JSON 结构里启发式找“像职位”的对象。
    规则：同时包含 (id 类字段) + (title 类字段)，并且再满足若干“职位特征”字段。
    """
    results: list[dict[str, Any]] = []
    for node in _iter_nodes(payload):
        if not isinstance(node, dict):
            continue
        job_id = _get_str(
            node,
            [
                "job_id",
                "jobId",
                "jobID",
                "jobUnionId",
                "id",
                "postId",
                "positionId",
                "position_id",
            ],
        )
        title = _get_str(node, ["job_title", "title", "name", "positionName", "position_name", "jobName"])
        if not job_id or not title:
            continue
        # 进一步用“职位常见字段”打分，避免把新闻/页面配置当作职位
        score = 0
        if _get_str(node, ["location", "city", "workLocation", "work_location", "locationName"]) or node.get("cityList"):
            score += 1
        if _get_str(node, ["department", "dept", "org", "organization", "businessGroup", "bg"]):
            score += 1
        if _get_str(node, ["publishTime", "updateTime", "createTime", "lastUpdateTime", "publishDate"]) or node.get(
            "refreshTime"
        ):
            score += 1
        if _get_str(
            node,
            [
                "jd",
                "description",
                "jobDescription",
                "job_desc",
                "requirement",
                "requirements",
                "jobDuty",
                "jobRequirement",
                "desc",
            ],
        ):
            score += 1
        if _get_str(node, ["jobType", "job_type", "positionType", "recruitType", "hiringType"]):
            score += 1

        # 至少命中 2 个特征字段才认为是职位对象
        if score >= 2:
            results.append(node)
    return results


def normalize_from_job_dict(d: dict[str, Any]) -> dict[str, Any]:
    job_id = _get_str(
        d, ["job_id", "jobId", "jobID", "jobUnionId", "id", "postId", "positionId", "position_id"]
    ) or "unknown"
    title = _get_str(d, ["job_title", "title", "name", "positionName", "position_name", "jobName"]) or "unknown"
    location = _get_list_str(d, ["location", "city", "cities", "workLocation", "work_location", "locationName"])
    if not location and isinstance(d.get("cityList"), list):
        location = [c.get("name", "").strip() for c in d["cityList"] if isinstance(c, dict) and c.get("name")]
    publish_date = _get_str(
        d,
        [
            "publish_date",
            "publishDate",
            "publishTime",
            "updateTime",
            "createTime",
            "lastUpdateTime",
            "refreshTime",
        ],
    )
    category_path = _get_list_str(d, ["category_path", "categoryPath", "category", "categories", "jobCategoryName"])
    detail_url = _get_str(d, ["detailUrl", "detail_url", "url", "jobUrl", "positionUrl", "link"])
    raw_text = _get_str(
        d,
        [
            "jd",
            "description",
            "jobDescription",
            "job_desc",
            "requirement",
            "requirements",
            "jobDuty",
            "jobRequirement",
            "desc",
        ],
    ) or ""
    return {
        "job_id": job_id,
        "job_title": title,
        "location": location,
        "publish_date": publish_date,
        "category_path": category_path,
        "detail_url": detail_url,
        "raw_jd_text": raw_text,
    }

