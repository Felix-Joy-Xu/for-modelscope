#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 models_all.json 的 Owner 字段提取贡献者长尾
================================================
不依赖用户资料 API（平台无公开 get_user）
直接统计：每个 Owner 的模型数、下载量、点赞、许可证分布
并与 meta_orgs.json 交叉，标记是否为组织
"""
import os, json, csv
from collections import defaultdict, Counter
from datetime import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")

print("加载 models_all.json ...")
with open(os.path.join(OUTPUT_DIR, "models_all.json"), "r", encoding="utf-8") as f:
    models = json.load(f)
print(f"  模型: {len(models):,}")

print("加载 meta_orgs.json ...")
with open(os.path.join(OUTPUT_DIR, "meta_orgs.json"), "r", encoding="utf-8") as f:
    orgs_data = json.load(f)
org_names = {o.get("Name", "").lower() for o in orgs_data if o.get("Name")}
org_info = {o.get("Name", "").lower(): o for o in orgs_data if o.get("Name")}
print(f"  组织: {len(org_names):,}")

# 聚合
stats = defaultdict(lambda: {
    "owner": "",
    "model_count": 0,
    "total_downloads": 0,
    "total_likes": 0,
    "licenses": Counter(),
    "first_created": None,
    "last_updated": None,
    "sample_models": [],
    "is_org_in_list": False,
    "org_model_nums_claimed": None,
})

for m in models:
    owner = m.get("Owner") or m.get("owner") or ""
    if not owner:
        continue
    key = owner.lower()
    s = stats[key]
    s["owner"] = owner  # 保留原始大小写
    s["model_count"] += 1
    s["total_downloads"] += int(m.get("Downloads") or m.get("downloads") or 0)
    s["total_likes"] += int(m.get("Likes") or m.get("likes") or 0)

    lic = m.get("License") or m.get("license") or ""
    if lic:
        s["licenses"][lic] += 1

    created = m.get("CreatedAt") or m.get("created_at") or ""
    updated = m.get("UpdatedAt") or m.get("updated_at") or ""
    if created:
        if s["first_created"] is None or str(created) < str(s["first_created"]):
            s["first_created"] = str(created)
    if updated:
        if s["last_updated"] is None or str(updated) > str(s["last_updated"]):
            s["last_updated"] = str(updated)

    if len(s["sample_models"]) < 3:
        mid = m.get("Id") or m.get("id") or m.get("Name") or ""
        s["sample_models"].append(mid)

# 标记是否在组织列表中
for key, s in stats.items():
    s["is_org_in_list"] = key in org_names
    if key in org_info:
        s["org_model_nums_claimed"] = org_info[key].get("ModelNums")

# 转为列表并排序
contributors = []
for key, s in stats.items():
    licenses = s["licenses"]
    top_lic = licenses.most_common(1)[0][0] if licenses else ""
    contributors.append({
        "owner": s["owner"],
        "owner_lower": key,
        "model_count": s["model_count"],
        "total_downloads": s["total_downloads"],
        "total_likes": s["total_likes"],
        "avg_downloads": round(s["total_downloads"] / s["model_count"], 1) if s["model_count"] else 0,
        "top_license": top_lic,
        "license_diversity": len(licenses),
        "first_created": s["first_created"] or "",
        "last_updated": s["last_updated"] or "",
        "is_org_in_list": s["is_org_in_list"],
        "org_model_nums_claimed": s["org_model_nums_claimed"],
        "sample_models": "|".join(s["sample_models"]),
        # 启发式：名称含常见个人特征 vs 组织特征
        "name_looks_personal": (
            not s["is_org_in_list"]
            and not any(x in key for x in [
                "lab", "ai", "org", "inc", "ltd", "corp", "team", "research",
                "university", "institute", "foundation", "community", "modelscope",
                "alibaba", "tencent", "baidu", "bytedance", "huawei", "xiaomi",
                "openai", "google", "meta", "microsoft", "nvidia", "hugging",
            ])
        ),
    })

contributors.sort(key=lambda x: (-x["model_count"], -x["total_downloads"]))

# 保存
json_path = os.path.join(OUTPUT_DIR, "contributors_all.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(contributors, f, ensure_ascii=False, indent=2)

csv_path = os.path.join(OUTPUT_DIR, "contributors_all.csv")
fields = [
    "owner", "model_count", "total_downloads", "total_likes", "avg_downloads",
    "top_license", "license_diversity", "first_created", "last_updated",
    "is_org_in_list", "name_looks_personal", "org_model_nums_claimed", "sample_models",
]
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(contributors)

# 统计摘要
n = len(contributors)
org_n = sum(1 for c in contributors if c["is_org_in_list"])
personal_n = sum(1 for c in contributors if c["name_looks_personal"])
other_n = n - org_n - personal_n

org_models = sum(c["model_count"] for c in contributors if c["is_org_in_list"])
personal_models = sum(c["model_count"] for c in contributors if c["name_looks_personal"])
other_models = sum(c["model_count"] for c in contributors) - org_models - personal_models

total_models = sum(c["model_count"] for c in contributors)
top10 = contributors[:10]
top10_share = sum(c["model_count"] for c in top10) / total_models if total_models else 0
top50_share = sum(c["model_count"] for c in contributors[:50]) / total_models if total_models else 0

# Gini
def gini(values):
    vals = sorted([v for v in values if v > 0])
    if not vals:
        return 0.0
    n = len(vals)
    total = sum(vals)
    cum = 0
    g = 0
    for i, v in enumerate(vals, 1):
        cum += v
        g += (2 * i - n - 1) * v
    return g / (n * total)

g = gini([c["model_count"] for c in contributors])

print("=" * 60)
print("贡献者长尾提取完成")
print("=" * 60)
print(f"  唯一 Owner 数:     {n:,}")
print(f"  在组织列表中:      {org_n:,} 人 / {org_models:,} 模型")
print(f"  启发式个人账号:    {personal_n:,} 人 / {personal_models:,} 模型")
print(f"  其他/未分类:       {other_n:,} 人 / {other_models:,} 模型")
print(f"  Top10 模型占比:    {top10_share*100:.1f}%")
print(f"  Top50 模型占比:    {top50_share*100:.1f}%")
print(f"  贡献者 Gini 系数:  {g:.3f}")
print()
print("  Top 15 贡献者:")
for i, c in enumerate(contributors[:15], 1):
    tag = "ORG" if c["is_org_in_list"] else ("PERSON?" if c["name_looks_personal"] else "OTHER")
    print(f"  {i:2d}. [{tag:7s}] {c['owner'][:30]:30s} models={c['model_count']:>5} dl={c['total_downloads']:>10}")
print()
print(f"  输出: contributors_all.json / contributors_all.csv")
print(f"  路径: {OUTPUT_DIR}")
