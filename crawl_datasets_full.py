import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
"""补充采集：数据集全库（按关键词分批，绕过3000上限）"""
import os, json, time, csv

TOKEN = MODELSCOPE_TOKEN
os.environ["MODELSCOPE_API_TOKEN"] = TOKEN

from modelscope.hub.api import HubApi

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
API = HubApi()

# 加载已有 3000 数据集，作为基础
existing_path = os.path.join(OUTPUT_DIR, "datasets_all.json")
if os.path.exists(existing_path):
    with open(existing_path, "r", encoding="utf-8") as f:
        existing = json.load(f)
    seen_ids = {d.get("id") or d.get("Id") for d in existing}
    print(f"已有 {len(existing)} 数据集, 去重池已建立")
else:
    existing, seen_ids = [], set()

# 5 个领域 × 多个搜索关键词，分批抓取
DOMAINS = {
    "nlp": ["llm", "chat", "qa", "translation", "summarization", "embedding", "instruction", "alpaca"],
    "multi-modal": ["vqa", "ocr", "image-caption", "image-text", "video", "caption"],
    "cv": ["classification", "detection", "segmentation", "face", "image", "ocr"],
    "audio": ["asr", "tts", "speech", "voice", "audio"],
    "science": ["protein", "molecule", "drug", "bio", "scientific"],
}

# 还有一些通用名目
COMMON = ["chinese", "alpaca", "sharegpt", "duie", "finetune", "train",
          "wiki", "math", "code", "medical", "legal", "pretrain",
          "zh", "en", "open", "qa", "instruction", "rag", "bench",
          "dev", "test", "eval", "reward", "safety", "ai", "agent"]

all_keywords = COMMON + [k for ks in DOMAINS.values() for k in ks]
print(f"将分 {len(all_keywords)} 个关键词批次抓取")

total_collected = list(existing)
total_seen = set(seen_ids)
request_count = 0
save_every = 5  # 每5个关键词保存一次

def save_datasets():
    save_json(total_collected)
    save_csv(total_collected)

def save_json(data):
    path = os.path.join(OUTPUT_DIR, "datasets_all.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_csv(data):
    path = os.path.join(OUTPUT_DIR, "datasets_all.csv")
    fields = sorted(data[0].keys()) if data else []
    if not fields:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in data:
            row = {k: (json.dumps(v, ensure_ascii=False) if hasattr(v,"isoformat") or isinstance(v,(list,dict)) else v)
                   for k, v in r.items()}
            try:
                w.writerow(row)
            except:
                pass

for i, kw in enumerate(all_keywords, 1):
    page = 1
    found_for_kw = 0
    err_count = 0
    while page * 50 <= 3000:
        try:
            result = API.list_datasets(page_size=50, page_number=page, search=kw)
            request_count += 1
            items = list(result.items) if hasattr(result, "items") else []
            if not items:
                break
            new_in_page = 0
            for item in items:
                d = item.to_dict() if hasattr(item, "to_dict") else item
                did = d.get("id") or d.get("Id")
                if did and did not in total_seen:
                    total_seen.add(did)
                    total_collected.append(d)
                    new_in_page += 1
                    found_for_kw += 1
            if not result.has_next or new_in_page == 0:
                break
            page += 1
            time.sleep(0.05)
        except Exception as e:
            msg = str(e)[:120]
            if "3000" in msg:
                break
            err_count += 1
            if err_count >= 2:
                print(f"  [{i}/{len(all_keywords)}] kw='{kw}' p{page} ERR: {msg}")
                break
            time.sleep(1)
            continue

    if found_for_kw > 0:
        print(f"  [{i}/{len(all_keywords)}] kw='{kw}': +{found_for_kw} (累计 {len(total_collected)})")
    else:
        if i % 10 == 0:
            print(f"  [{i}/{len(all_keywords)}] kw='{kw}': +0 (累计 {len(total_collected)})")

    if i % save_every == 0:
        save_datasets()
        print(f"    -> 已保存 (累计 {len(total_collected)} 条, 第 {i} 关键词之后)")

# 最终保存
save_datasets()
print()
print("="*60)
print(f"完成。总数据集: {len(total_collected):,} 条")
print(f"已保存: datasets_all.json, datasets_all.csv")
print("="*60)