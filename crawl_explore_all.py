import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
"""扩充采集：Skills 全集（76K）+ MCP 全集（10K）+ 数据集补充"""
import os, json, time, csv
TOKEN = MODELSCOPE_TOKEN
os.environ["MODELSCOPE_API_TOKEN"] = TOKEN
from modelscope.hub.api import HubApi
from modelscope_hub.types import RepoType

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
API = HubApi()


def _clean(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def save_all(records, base_name):
    if not records:
        return
    with open(os.path.join(OUTPUT_DIR, f"{base_name}_all.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    fields = sorted(records[0].keys()) if records else []
    with open(os.path.join(OUTPUT_DIR, f"{base_name}_all.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: _clean(v) for k, v in r.items()})
    print(f"  saved {len(records):,} 条 -> {base_name}_all.json/csv")


def crawl_by_sort(repo_type, base_name):
    """用多种 sort + search 组合绕过 3000 上限采集"""
    seen = set()
    total = []

    sorts = [None, "likes", "downloads", "recently_modified",
             "download_count", "display_name", "popular"]
    searches = [None, "ai", "image", "video", "code", "agent", "audio",
                "vision", "ocr", "translate", "llm", "embed",
                "music", "diffusion", "flux", "sd", "lora",
                "asr", "tts", "voice", "distill", "reason",
                "math", "physics", "scientific", "write",
                "class", "segment", "detection"]

    cycle = 0
    for sort in sorts:
        for search in searches:
            page = 1
            consecutive_empty = 0
            while page * 50 <= 3000:
                try:
                    kwargs = {"repo_type": repo_type, "page_size": 50, "page_number": page}
                    if sort:
                        kwargs["sort"] = sort
                    if search:
                        kwargs["search"] = search
                    r = API.list_repos(**kwargs)
                    items = list(r.items) if hasattr(r, "items") else []
                    if not items:
                        break
                    new_in_page = 0
                    for item in items:
                        d = item.to_dict() if hasattr(item, "to_dict") else item
                        rid = d.get("id") or d.get("Id")
                        if rid and rid not in seen:
                            seen.add(rid)
                            total.append(d)
                            new_in_page += 1
                    if new_in_page == 0:
                        consecutive_empty += 1
                        if consecutive_empty >= 2:
                            break
                    else:
                        consecutive_empty = 0
                    if not r.has_next:
                        break
                    page += 1
                    time.sleep(0.03)
                except Exception as e:
                    if "3000" in str(e):
                        break
                    break

            cycle += 1
            if total and cycle % 10 == 0:
                print(f"  [{base_name}] sort={sort} search={search}: 累计 {len(total):,}")

    save_all(total, base_name)
    return total


# 1. Skills（76K总库）
print("="*60)
print("1. 采集 Skills 全集")
print("="*60)
skills = crawl_by_sort(RepoType.SKILL, "skills")

# 2. MCP（10K总库）
print("\n" + "="*60)
print("2. 采集 MCP 全集")
print("="*60)
mcps = crawl_by_sort(RepoType.MCP, "mcps")

# 3. 补充数据集（已有24K，目标38K）
print("\n" + "="*60)
print("3. 扩充数据集到全库")
print("="*60)

# 先加载已有数据集
ds_path = os.path.join(OUTPUT_DIR, "datasets_all.json")
with open(ds_path, "r", encoding="utf-8") as f:
    existing_ds = json.load(f)
ds_seen = {d.get("id") for d in existing_ds}
ds_total = list(existing_ds)
print(f"  已有 {len(existing_ds):,}")

# 用更细分关键词 + 各种 sort 拉新数据
EXTRA_KW = [
    "qa", "judge", "summarize", "translate", "embed", "vision",
    "wiki", "code", "math", "instruction", "alpaca", "cot",
    "reason", "logic", "agent", "tool", "reward", "preference",
    "synthetic", "synth", "instruction", "wiki", "stack",
    "open", "share", "common", "few", "low", "zero", "high",
    "indomain", "outdomain", "natural", "instructiontune",
    "human", "gpt4", "generated", "annotated", "labeled",
    "alignment", "rlhf", "dpo", "preference", "safety",
    "qa", "ric", "task", "fewshot", "pp",
    "qa", "sharegpt", "hermes", "dolly", "openhermes",
    "fin", "medical", "legal", "bio", "chemical",
    "qwen", "llama", "yi", "deepseek", "chatglm", "baichuan",
    "x", "1", "2", "3", "5", "7", "v1", "v2", "v3", "new",
    "english", "chinese", "japanese", "korean",
    "bilingual", "monolingual", "multilingual", "code",
    "image", "video", "audio", "text", "tabular",
    "ecology", "industry", "scifi",
]

for i, kw in enumerate(EXTRA_KW, 1):
    page = 1
    found = 0
    while page * 50 <= 3000:
        try:
            r = API.list_repos(repo_type=RepoType.DATASET, page_size=50, page_number=page, search=kw)
            items = list(r.items) if hasattr(r, "items") else []
            if not items:
                break
            for item in items:
                d = item.to_dict() if hasattr(item, "to_dict") else item
                did = d.get("id") or d.get("Id")
                if did and did not in ds_seen:
                    ds_seen.add(did)
                    ds_total.append(d)
                    found += 1
            if not r.has_next:
                break
            page += 1
            time.sleep(0.03)
        except:
            break

    if found > 0:
        print(f"  [{i}/{len(EXTRA_KW)}] kw='{kw}': +{found} (累计 {len(ds_total):,})")

    if i % 20 == 0:
        save_all(ds_total, "datasets")

save_all(ds_total, "datasets")

print()
print("="*60)
print("扩充完成汇总")
print("="*60)
print(f"  Skills:  {len(skills):,} 条 (总库 76,122)")
print(f"  MCP:     {len(mcps):,} 条 (总库 9,767)")
print(f"  数据集:  {len(ds_total):,} 条 (总库 38,150)")