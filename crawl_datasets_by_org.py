import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
"""扩张采集：数据集按 500 个组织 owner 分批拉（绕过3000上限）"""
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
print(f"已有 {len(existing)} 数据集")

# 加载组织列表
with open(os.path.join(OUTPUT_DIR, "meta_orgs.json"), "r", encoding="utf-8") as f:
    orgs_data = json.load(f)
orgs = [o.get("Name") for o in orgs_data if o.get("Name")]
print(f"将遍历 {len(orgs)} 个组织")


def _clean(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v

def save():
    with open(os.path.join(OUTPUT_DIR, "datasets_all.json"), "w", encoding="utf-8") as f:
        json.dump(total_collected, f, ensure_ascii=False, indent=2)
    if total_collected:
        fields = sorted(total_collected[0].keys())
        with open(os.path.join(OUTPUT_DIR, "datasets_all.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in total_collected:
                w.writerow({k: _clean(v) for k, v in r.items()})

total_new = 0
for i, org in enumerate(orgs, 1):
    if not org:
        continue
    page = 1
    org_new = 0
    err_count = 0
    while page * 50 <= 3000:
        try:
            r = API.list_datasets(owner=org, page_size=50, page_number=page)
            items = list(r.items) if hasattr(r, "items") else []
            if not items:
                break
            for item in items:
                d = item.to_dict() if hasattr(item, "to_dict") else item
                did = d.get("id") or d.get("Id")
                if did and did not in total_seen:
                    total_seen.add(did)
                    total_collected.append(d)
                    org_new += 1
            if not r.has_next:
                break
            page += 1
            time.sleep(0.03)
        except Exception as e:
            if "3000" in str(e):
                break
            err_count += 1
            if err_count >= 2:
                break
            time.sleep(1)

    if org_new > 0:
        total_new += org_new
        print(f"  [{i}/{len(orgs)}] {org}: +{org_new} (累计 {len(total_collected)})")
    elif i % 50 == 0:
        print(f"  [{i}/{len(orgs)}] {org}: +0 (累计 {len(total_collected)})")

    if i % 20 == 0:
        save()

save()
print()
print("="*60)
print(f"扩充完成")
print(f"  原有:  {len(existing):,}")
print(f"  新增:  {total_new:,}")
print(f"  总计:  {len(total_collected):,} 数据集")
print("="*60)