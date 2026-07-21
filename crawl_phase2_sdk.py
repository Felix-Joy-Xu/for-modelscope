import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
魔搭 Phase 2 (SDK版)：资源元数据批量采集
==========================================
使用 modelscope Python SDK，Token 直接通过环境变量传
采集：
  1. 全部数据集元数据（list_datasets 全量分页）
  2. 全部模型元数据（遍历 500 个组织，按 owner 收集模型）
  3. 创空间（studios）— SDK 暂无，需要用 dolphin API
输出:
  modelscope_output/
    datasets_all.json / .csv
    models_all.json / .csv
    phase2_state.json  采集进度（断点续传）
"""

import csv
import json
import os
import time
from datetime import datetime

# 设置 Token
TOKEN = MODELSCOPE_TOKEN
os.environ["MODELSCOPE_API_TOKEN"] = TOKEN

from modelscope.hub.api import HubApi

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
STATE_FILE = os.path.join(OUTPUT_DIR, "phase2_state.json")

API = HubApi()
PAGE_SIZE = 100
DELAY = 0.05  # SDK调用间隔（秒）


# ============================================================================
# 状态管理
# ============================================================================

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"datasets_page": 0, "models_org_index": 0}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================================
# 输出
# ============================================================================

def save_csv(records, filename, fields=None):
    if not records:
        return

    def _clean(v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return v

    path = os.path.join(OUTPUT_DIR, filename)
    if fields is None:
        first = records[0]
        if not isinstance(first, dict):
            first = first.to_dict()
        fields = sorted(first.keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in records:
            if not isinstance(r, dict):
                r = r.to_dict()
            row = {k: _clean(v) for k, v in r.items()}
            w.writerow(row)
    print(f"  CSV: {filename} ({len(records)} 条)")


def save_json(records, filename):
    path = os.path.join(OUTPUT_DIR, filename)

    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(x) for x in o]
        if hasattr(o, "isoformat"):  # datetime
            return o.isoformat()
        return o

    data = [_clean(r if isinstance(r, dict) else r.to_dict()) for r in records]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  JSON: {filename} ({len(data)} 条)")


# ============================================================================
# 数据集采集（全量分页）
# ============================================================================

def crawl_datasets():
    print("=" * 60)
    print("1. 全部数据集元数据（SDK list_datasets）")
    print("=" * 60)
    all_datasets = []
    page = 1
    total = None

    err_count = 0
    while True:
        try:
            result = API.list_datasets(page_size=PAGE_SIZE, page_number=page)
            err_count = 0
        except Exception as e:
            msg = str(e)[:100]
            if "must be <= 3000" in msg or "3000" in msg:
                print(f"  [LIMIT] {page * PAGE_SIZE} > 3000, 停止 at p{page}")
                break
            err_count += 1
            if err_count >= 3:
                print(f"  [ERR] 3 次失败，停止: {msg}")
                break
            print(f"  [ERR] p{page}: {msg}")
            time.sleep(2)
            continue

        items = result.items if hasattr(result, "items") else []
        if total is None:
            total = result.total_count if hasattr(result, "total_count") else "?"
            print(f"  Total datasets: {total}")

        if not items:
            print(f"  p{page}: 0 items, end")
            break

        for item in items:
            d = item.to_dict() if hasattr(item, "to_dict") else item
            all_datasets.append(d)

        if page % 10 == 0 or page == 1:
            print(f"  p{page}: +{len(items)} (累计 {len(all_datasets)}/{total})")

        if not result.has_next:
            print(f"  p{page}: has_next=False, end")
            break

        page += 1
        time.sleep(DELAY)

    if all_datasets:
        save_json(all_datasets, "datasets_all.json")
        save_csv(all_datasets, "datasets_all.csv")
    return all_datasets


# ============================================================================
# 模型采集（按组织遍历）
# ============================================================================

def crawl_models_by_orgs(orgs):
    print("=" * 60)
    print(f"2. 模型元数据（遍历 {len(orgs)} 个组织）")
    print("=" * 60)
    all_models = []
    seen_ids = set()
    state = load_state()
    start_idx = state.get("models_org_index", 0)

    if start_idx > 0:
        # 加载已有记录以便去重
        existing = os.path.join(OUTPUT_DIR, "models_all.json")
        if os.path.exists(existing):
            with open(existing, "r", encoding="utf-8") as f:
                all_models = json.load(f)
                seen_ids = {m.get("Id") or m.get("id") for m in all_models}
        print(f"  断点续传: 已有 {len(all_models)} 模型, 从组织 #{start_idx} 开始")

    for i, org in enumerate(orgs[start_idx:], start=start_idx):
        if not org:
            continue
        try:
            r = API.list_models(owner_or_group=org, page_size=100, page_number=1)
            if isinstance(r, dict):
                models = r.get("Models", [])
                tc = r.get("TotalCount", 0)
            else:
                models = r.items if hasattr(r, "items") else []
                tc = r.total_count if hasattr(r, "total_count") else 0

            new_count = 0
            for m in models:
                mid = m.get("Id") or m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_models.append(m)
                    new_count += 1
            print(f"  [{i+1}/{len(orgs)}] {org}: TC={tc} 新增={new_count} 累计={len(all_models)}")

            # 处理第二页及之后
            if tc > 100:
                page = 2
                while page * 100 < tc + 100 and page * 100 <= 3000:
                    try:
                        r2 = API.list_models(owner_or_group=org, page_size=100, page_number=page)
                        if isinstance(r2, dict):
                            models2 = r2.get("Models", [])
                        else:
                            models2 = r2.items if hasattr(r2, "items") else []
                        if not models2:
                            break
                        for m in models2:
                            mid = m.get("Id") or m.get("id")
                            if mid and mid not in seen_ids:
                                seen_ids.add(mid)
                                all_models.append(m)
                        page += 1
                        time.sleep(DELAY)
                    except Exception as e:
                        msg = str(e)[:60]
                        if "3000" in msg:
                            break
                        print(f"      [ERR] p{page}: {msg}")
                        break

            # 保存状态
            state["models_org_index"] = i + 1
            save_state(state)

            # 每10个组织保存一次
            if (i + 1) % 10 == 0:
                save_json(all_models, "models_all.json")
                save_csv(all_models, "models_all.csv")

            time.sleep(DELAY)
        except Exception as e:
            print(f"  [{i+1}/{len(orgs)}] {org}: ERR {str(e)[:60]}")
            time.sleep(0.5)

    if all_models:
        save_json(all_models, "models_all.json")
        save_csv(all_models, "models_all.csv")
    return all_models


# ============================================================================
# 主控
# ============================================================================

def main():
    print("=" * 60)
    print("魔搭 Phase 2 (SDK版): 资源元数据采集")
    print("=" * 60)

    state = load_state()
    print(f"已采集: datasets_page={state.get('datasets_page',0)} org_index={state.get('models_org_index',0)}")

    # 加载组织列表
    orgs_path = os.path.join(OUTPUT_DIR, "meta_orgs.json")
    if os.path.exists(orgs_path):
        with open(orgs_path, "r", encoding="utf-8") as f:
            orgs_data = json.load(f)
        orgs = [o.get("Name", "") for o in orgs_data if o.get("Name")]
        print(f"加载 {len(orgs)} 个组织")
    else:
        print("警告: 没有 meta_orgs.json, 用默认组织列表")
        orgs = ["qwen", "deepseek-ai", "ZhipuAI", "AI-ModelScope", "damo",
                "alibaba-pai", "Tencent-Hunyuan", "iic"]

    # 1. 数据集 - 检查是否已完成（断点续传）
    datasets = []
    if state.get("datasets_done", False) and os.path.exists(os.path.join(OUTPUT_DIR, "datasets_all.json")):
        print("\n[跳过] 数据集已采集")
    else:
        datasets = crawl_datasets()
        state["datasets_done"] = True
        save_state(state)

    # 2. 模型 - 检查是否已完成（断点续传）
    models = []
    if state.get("models_org_index", 0) >= len(orgs) and os.path.exists(os.path.join(OUTPUT_DIR, "models_all.json")):
        print("\n[跳过] 模型已采集")
    else:
        models = crawl_models_by_orgs(orgs)

    # 汇总
    print()
    print("=" * 60)
    print("采集完成")
    print("=" * 60)
    print(f"  数据集: {len(datasets):,} 条")
    print(f"  模型:   {len(models):,} 条")
    print(f"  输出:   {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()