import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
魔搭 Phase 2：资源元数据批量采集
================================
使用 dolphin/modelsWithCollections API（公开，未登录可用）
采集：模型列表 + 组织列表 + 许可证列表 + 任务分类

输出:
  modelscope_output/
    meta_models.json / .csv    全部模型元数据
    meta_datasets.json / .csv  全部数据集元数据（同 API, Type=Dataset）
    meta_orgs.json             组织/机构列表
    meta_licenses.json         支持的许可证
    meta_tasks.json            任务/领域分类
    phase2_state.json          采集进度（断点续传）
"""

import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

# ============================================================================
# 配置
# ============================================================================

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

STATE_FILE = os.path.join(OUTPUT_DIR, "phase2_state.json")

BASE = "https://www.modelscope.cn"
MODELS_API = f"{BASE}/api/v1/dolphin/modelsWithCollections"
LICENSES_API = f"{BASE}/api/v1/licenses"
TASKS_API = f"{BASE}/api/v1/tasks"
ORG_TAGS_API = f"{BASE}/api/v1/models/orgTags"

PAGE_SIZE = 100
MAX_PAGES = 50000
DELAY = 0.1

HEADERS_DEFAULT = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": f"{BASE}/models",
    "x-modelscope-accept-language": "zh_CN",
}

# Phase 时间边界
PHASE_B = datetime(2024, 3, 1, tzinfo=timezone.utc)

# ============================================================================
# 状态管理
# ============================================================================

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"models_page": 0, "datasets_page": 0}

def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ============================================================================
# API 客户端
# ============================================================================

# Token（仅用于分页，不暴露在代码中）
TOKEN = MODELSCOPE_TOKEN

class ModelScopeClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS_DEFAULT)
        self.csrf_token = None
        self._refresh_csrf()

    def _refresh_csrf(self):
        try:
            r = self.session.get(f"{BASE}/models", timeout=30)
            tok = self.session.cookies.get("csrf_token", "")
            self.csrf_token = tok.replace("%3D", "=")
            # 设置 token cookie（关键：domain 不要前导点）
            self.session.cookies.set("token", TOKEN, domain="modelscope.cn")
            self.session.cookies.set("ms_token", TOKEN, domain="modelscope.cn")
        except:
            pass

    def _headers(self, extra=None):
        h = extra or {}
        if self.csrf_token:
            h["x-csrf-token"] = self.csrf_token
        return h

    def get(self, url: str, params=None, **kwargs) -> Optional[dict]:
        try:
            r = self.session.get(url, params=params, headers=self._headers(),
                                timeout=kwargs.pop("timeout", 15), **kwargs)
            if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
                return r.json()
            if r.status_code == 403:
                self._refresh_csrf()
            return None
        except:
            return None

    def put(self, url: str, json_data: dict, **kwargs) -> Optional[dict]:
        try:
            r = self.session.put(url, json=json_data, headers=self._headers(),
                                timeout=kwargs.pop("timeout", 15), **kwargs)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 403:
                self._refresh_csrf()
            return None
        except:
            return None

    def fetch_list(self, url: str, page_size=PAGE_SIZE, extra_body=None,
                   max_pages=MAX_PAGES, start_page=0, label="list") -> List[dict]:
        """通用分页采集"""
        all_items = []
        page = start_page + 1 if start_page > 0 else 1
        consecutive_empty = 0

        body = {"PageSize": page_size, "PageNumber": page}
        if extra_body:
            body.update(extra_body)

        while page <= max_pages:
            body["PageNumber"] = page
            data = self.put(url, json_data=body)
            if not data or not data.get("Success"):
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                time.sleep(DELAY * 3)
                continue

            dd = data.get("Data", {})
            items = dd.get("ModelCollection", []) or dd.get("list", [])

            if not items:
                break

            count_before = len(all_items)
            for item in items:
                coll = item.get("Collection", {}) or item
                record = self._parse_item(coll)
                if record:
                    all_items.append(record)

            new_count = len(all_items) - count_before
            if page % 10 == 0 or new_count == 0:
                tc = dd.get("TotalCount", "?")
                print(f"  [{label}] p{page}: +{new_count} 累计 {len(all_items)} (总 {tc})")

            if new_count == 0:
                consecutive_empty += 1
                if consecutive_empty >= 5:
                    break
            else:
                consecutive_empty = 0

            page += 1
            time.sleep(DELAY)

        return all_items

    def _parse_item(self, coll: dict) -> Optional[dict]:
        """将 Collection 条目转为扁平模型记录"""
        name = coll.get("Name", "") or coll.get("FullName", "")
        path = coll.get("Path", "")
        if not name and not path:
            return None

        # 基本字段
        gmt_created = coll.get("GmtCreated", "") or coll.get("gmtCreated", "")
        dt = None
        if gmt_created:
            try:
                dt = datetime.fromisoformat(gmt_created.replace("Z", "+00:00"))
            except:
                pass

        # Organization
        org = coll.get("Organization", {}) or {}

        # 从 CollectionElements 获取子级模型元数据
        ce = coll.get("CollectionElements", {}) or {}
        elist = ce.get("CollectionElementVoList", []) or ce.get("list", [])

        # 聚合子级元数据
        licenses = []
        tags = []
        total_downloads = 0
        domains = []
        tasks = []
        providers = []

        for el in elist:
            info = el.get("ElementInfo", {}) or {}
            lic = info.get("License") or info.get("DatasetLicense", "")
            if lic:
                licenses.append(lic)
            t = info.get("Tags") or info.get("DatasetUserDefineTags") or []
            if isinstance(t, list):
                tags.extend(t)
            dl = info.get("Downloads") or info.get("DatasetDownloads", 0) or 0
            total_downloads += dl
            d = info.get("DomainName") or info.get("DatasetDomainName", "")
            if d:
                domains.append(d)
            task = info.get("TaskName", "")
            if task:
                tasks.append(task)
            prov = info.get("Provider", "")
            if prov:
                providers.append(prov)

        record = {
            "path": path,
            "name": name,
            "owner": coll.get("Owner", ""),
            "creator": coll.get("Creator", ""),
            "nickname": coll.get("NickName", ""),
            "org_name": org.get("CnName", "") or org.get("Name", ""),
            "org_avatar": org.get("Avatar", ""),
            "element_count": coll.get("ElementCount", 0),
            "view_count": coll.get("ViewCount", 0),
            "favorite_count": coll.get("FavoriteCount", 0),
            "top_type": coll.get("TopType", ""),
            "gmt_created": gmt_created,
            "gmt_modified": coll.get("GmtModified", ""),
            "phase": "B" if (dt and dt >= PHASE_B) else ("A" if dt else "unknown"),
            "license": "|".join(set(licenses)),
            "tags": "|".join(set(tags)),
            "domains": "|".join(set(domains)),
            "tasks": "|".join(set(tasks)),
            "providers": "|".join(set(providers)),
            "total_downloads": total_downloads,
        }
        return record


# ============================================================================
# 输出
# ============================================================================

def save_json(data, filename):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {filename} ({len(data)} 条)")

def save_csv(records, filename):
    if not records:
        return
    path = os.path.join(OUTPUT_DIR, filename)
    keys = sorted(records[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)
    print(f"  CSV: {filename} ({len(records)} 条)")


# ============================================================================
# 主控
# ============================================================================

def main():
    print("=" * 60)
    print("魔搭 Phase 2: 资源元数据批量采集")
    print("=" * 60)

    client = ModelScopeClient()
    state = load_state()

    # ---- 1. 许可证 ----
    print("\n--- 1. 许可证 ---")
    r = client.get(LICENSES_API)
    if r and r.get("Data"):
        licenses = r["Data"].get("Licenses", [])
        save_json(licenses, "meta_licenses.json")
        print(f"  {len(licenses)} 个许可证")

    # ---- 2. 任务分类 ----
    print("\n--- 2. 任务/领域分类 ---")
    r = client.get(TASKS_API, params={"PageNumber": 1})
    if r and r.get("Data"):
        tasks = r["Data"].get("Domains", [])
        save_json(tasks, "meta_tasks.json")
        print(f"  {len(tasks)} 个领域")

    # ---- 3. 组织/机构列表 ----
    print("\n--- 3. 组织列表 ---")
    r = client.get(ORG_TAGS_API, params={"PageSize": 500, "PageNumber": 1})
    if r and r.get("Data"):
        orgs = r["Data"].get("list", [])
        save_json(orgs, "meta_orgs.json")
        print(f"  {len(orgs)} 个组织")

    # ---- 4. 模型列表 ----
    print("\n--- 4. 模型列表 ---")
    start_page = state.get("models_page", 0)
    if start_page > 0:
        print(f"  (断点续传，从第 {start_page} 页开始)")
    models = client.fetch_list(MODELS_API, label="models", start_page=start_page)
    if models:
        save_json(models, "meta_models.json")
        save_csv(models, "meta_models.csv")
    state["models_page"] = (start_page // PAGE_SIZE) + (len(models) // PAGE_SIZE) + 1
    save_state(state)

    # ---- 5. 数据集列表 ----
    print("\n--- 5. 数据集列表 ---")
    start_page = state.get("datasets_page", 0)
    datasets = client.fetch_list(MODELS_API, label="datasets",
                                 extra_body={"Type": "Dataset"}, start_page=start_page)
    if datasets:
        save_json(datasets, "meta_datasets.json")
        save_csv(datasets, "meta_datasets.csv")
    state["datasets_page"] = (start_page // PAGE_SIZE) + (len(datasets) // PAGE_SIZE) + 1
    save_state(state)

    # ---- 汇总 ----
    print("\n" + "=" * 60)
    print("采集完成")
    print("=" * 60)
    print(f"  许可证:   {os.path.getsize(os.path.join(OUTPUT_DIR,'meta_licenses.json')):,} bytes")
    lic_path = os.path.join(OUTPUT_DIR, "meta_licenses.json")
    if os.path.exists(lic_path):
        with open(lic_path) as f:
            lic = json.load(f)
        print(f"           {len(lic)} 条")

    import glob
    for f in sorted(glob.glob(os.path.join(OUTPUT_DIR, "meta_*.csv"))):
        fn = os.path.basename(f)
        s = os.path.getsize(f)
        print(f"  {fn:30s} {s:>10,} bytes")

    print(f"\n输出: {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()