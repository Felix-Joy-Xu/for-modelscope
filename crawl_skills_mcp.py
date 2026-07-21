import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
"""扩充：Skills 和 MCP 用更细的 sort 组合绕 3000 上限"""
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

# 加载已有
def load_existing(name):
    p = os.path.join(OUTPUT_DIR, f"{name}_all.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# 更多 sort 组合 + 多关键词
ALL_SORTS = [None, "likes", "downloads", "recently_modified", "popular", "display_name"]
ALL_KW = [
    None,
    "ai", "image", "video", "code", "agent", "audio", "vision",
    "ocr", "translate", "llm", "embed", "music", "diffusion",
    "flux", "sd", "lora", "asr", "tts", "voice",
    "math", "physics", "scientific", "write", "class",
    "segment", "detection", "rag", "tool", "mcp",
    "python", "js", "javascript", "java", "go", "rust", "c+",
    "opencompass", "swift", "finetune", "train", "eval",
    "benchmark", "leaderboard", "chat", "assistant",
    "design", "art", "photo", "video-edit", "image-edit",
    "response", "reasoner", "math-reasoner",
    "1", "2", "3", "4", "5", "7",
    "multilingual", "english", "chinese", "japanese",
    "flux", "diff", "embed", "rerank",
]

def expand(repo_type, base_name):
    existing = load_existing(base_name)
    seen = {r.get("id") or r.get("Id") for r in existing}
    total = list(existing)
    print(f"已有 {len(existing):,}")

    cycle = 0
    for sort in ALL_SORTS:
        for kw in ALL_KW:
            page = 1
            consecutive_empty = 0
            while page * 50 <= 3000:
                try:
                    kwargs = {"repo_type": repo_type, "page_size": 50, "page_number": page}
                    if sort:
                        kwargs["sort"] = sort
                    if kw:
                        kwargs["search"] = kw
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
                    time.sleep(0.02)
                except:
                    break
            cycle += 1
            if cycle % 20 == 0:
                print(f"  [{base_name}] sort={sort} kw={kw}: 累计 {len(total):,}")
                save_all(total, base_name)

    save_all(total, base_name)
    print(f"  {base_name} 完成: {len(total):,}")
    return total

print("="*60)
print("1. 扩充 Skills（当前 13K / 总库 76K）")
print("="*60)
skills = expand(RepoType.SKILL, "skills")

print()
print("="*60)
print("2. 扩充 MCP（当前 696 / 总库 9.7K）")
print("="*60)
mcps = expand(RepoType.MCP, "mcps")

print()
print("="*60)
print("完成")
print("="*60)
print(f"  Skills: {len(skills):,}")
print(f"  MCP:    {len(mcps):,}")