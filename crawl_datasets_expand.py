import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
"""扩张采集：数据集按 更多关键词 + 多种排序 + 按owner分组"""
import os, json, time, csv

TOKEN = MODELSCOPE_TOKEN
os.environ["MODELSCOPE_API_TOKEN"] = TOKEN
from modelscope.hub.api import HubApi

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
API = HubApi()

# 加载已有数据
with open(os.path.join(OUTPUT_DIR, "datasets_all.json"), "r", encoding="utf-8") as f:
    existing = json.load(f)
    total_collected = list(existing)
    total_seen = {d.get("id") or d.get("Id") for d in existing}
print(f"已有 {len(existing)} 数据集, 继续扩充")

# 新增更多关键词 - 多元化角度
EXTRA_KEYWORDS = [
    # 工具/框架
    "opencompass", "swift", "llamafactory", "agent", "tool", "rag",
    "chain", "eval", "benchmark", "leaderboard", "finbench",
    # 语言
    "english", "englishchinese", "chineseenglish", "zh-en", "cc",
    "indonesian", "japanese", "korean", "french", "arabic", "spanish",
    # 行业/领域
    "finance", "banking", "legal", "medical", "health", "education",
    "agriculture", "env", "geo", "city", "physics", "chemistry",
    "geospatial", "remote", "satellite",
    # 任务/类型
    "labeled", "annotated", "annotation", "tagged", "supervised",
    "unsupervised", "preference", "dpo", "rlhf", "sft", "alignment",
    "pinkit", "pair", "instructiontuning", "fewshot", "zeroshot",
    # 来源/形式
    "paper", "research", "survey", "open", "public", "synthetic",
    "real", "crawl", "scrape", "collected", "merged", "clean",
    # 内容类型
    "table", "csv", "json", "txt", "image", "video", "audio",
    "webpage", "code", "document", "pdf", "qa", "dialogue",
    "conversation", "chatlog", "conversation", "multiturn",
    "summarize", "rewrite", "stylize", "paraphrase",
    # 模型家族
    "qwen", "llama", "baichuan", "chatglm", "glm", "deepseek",
    "yi", "internlm", "mistral", "phi", "gemma", "solar",
    "wenetspeech", "wenet", "whisper", "jasper",
    # 其他
    "reward", "preference", "ranking", "score", "judge",
    "common", "general", "domain", "vertical", "industry",
    "openimage", "openvideo", "opentext", "openaudio",
    "ocr", "abstractive", "extractive",
    "qa", "qa2", "qaa", "commonsense", "reason", "reasoning",
    "logic", "mathematical", "calculation", "numerical",
    "word", "char", "token", "lex", "syntax", "semantic",
    "edges", "graph", "tree", "triples", "rdf", "owl",
    "ner", "pos", "dependency", "syntax", "parsing", "wordseg",
    "spelling", "grammar", "coreference", "resolve",
    "virus", "pandemic", "covid", "genome",
    "metabolite", "drugbank", "chembl",
    "pertask", "fewshot", "lowshot", "transferlearning",
    "domain", "few", "low", "transfer",
    # 这些已经用过的，跳过
]

print(f"将搜索 {len(EXTRA_KEYWORDS)} 个新关键词")

save_every = 5

def save():
    with open(os.path.join(OUTPUT_DIR, "datasets_all.json"), "w", encoding="utf-8") as f:
        json.dump(total_collected, f, ensure_ascii=False, indent=2)
    # CSV
    if total_collected:
        fields = sorted(total_collected[0].keys())
        with open(os.path.join(OUTPUT_DIR, "datasets_all.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in total_collected:
                row = {k: (r[k].isoformat() if hasattr(r[k], "isoformat")
                          else (json.dumps(r[k], ensure_ascii=False) if isinstance(r[k], (list, dict)) else r[k]))
                       for k in r}
                w.writerow(row)

import json as _j

for i, kw in enumerate(EXTRA_KEYWORDS, 1):
    page = 1
    found_for_kw = 0
    err_count = 0
    while page * 50 <= 3000:
        try:
            result = API.list_datasets(page_size=50, page_number=page, search=kw)
            items = list(result.items) if hasattr(result, "items") else []
            if not items:
                break
            for item in items:
                d = item.to_dict() if hasattr(item, "to_dict") else item
                did = d.get("id") or d.get("Id")
                if did and did not in total_seen:
                    total_seen.add(did)
                    total_collected.append(d)
                    found_for_kw += 1
            if not result.has_next:
                break
            page += 1
            time.sleep(0.05)
        except Exception as e:
            if "3000" in str(e):
                break
            err_count += 1
            if err_count >= 2:
                break
            time.sleep(1)
            continue

    if found_for_kw > 0:
        print(f"  [{i}/{len(EXTRA_KEYWORDS)}] kw='{kw}': +{found_for_kw} (累计 {len(total_collected)})")
    elif i % 10 == 0:
        print(f"  [{i}/{len(EXTRA_KEYWORDS)}] kw='{kw}': +0 (累计 {len(total_collected)})")

    if i % save_every == 0:
        save()
        print(f"    -> 保存 (累计 {len(total_collected)})")

save()
print()
print("="*60)
print(f"扩充完成。总数据集: {len(total_collected):,} 条 (从 {len(existing)} 扩到)")
print("="*60)