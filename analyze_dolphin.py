"""分析 dolphin API 返回的模型字段详情"""
import json

with open("modelscope_output/_dolphin_p1_sample.json", "r", encoding="utf-8") as f:
    d = json.load(f)

mc = d["Data"]["ModelCollection"]
print(f"TotalCount: {d['Data']['TotalCount']}, This page: {len(mc)}\n")

for i, item in enumerate(mc[:3]):
    coll = item.get("Collection", {})
    print(f"--- Model {i+1} ---")
    print(f"  Name: {coll.get('Name','')}")
    print(f"  Path: {coll.get('Path','')}")
    print(f"  Owner: {coll.get('Owner','')}")
    print(f"  Creator: {coll.get('Creator','')}")
    print(f"  Views: {coll.get('ViewCount',0)}")
    print(f"  Favs: {coll.get('FavoriteCount',0)}")
    print(f"  Elements: {coll.get('ElementCount',0)}")
    print(f"  TopType: {coll.get('TopType','')}")

    # CollectionElements 内部的模型元数据
    ce = coll.get("CollectionElements", {})
    elist = ce.get("CollectionElementVoList", [])
    if elist:
        e = elist[0]
        info = e.get("ElementInfo", {})
        print(f"  ElementInfo keys: {list(info.keys())[:20]}")
        highlights = ["Id", "Downloads", "License", "Tags", "GmtModified",
                      "Provider", "DomainName", "Score", "ChinesName",
                      "Description", "ModelName"]
        for k in highlights:
            if k in info:
                v = info[k]
                if isinstance(v, str):
                    print(f"    {k}: {v[:70]}")
                elif isinstance(v, list):
                    print(f"    {k}: list({len(v)})")
                    if v and isinstance(v[0], str):
                        print(f"      items: {v[:5]}")
                else:
                    print(f"    {k}: {v}")
    print()

# 检查 Organization 信息
org = mc[0]["Collection"].get("Organization", {})
print("Organization:", json.dumps(org, ensure_ascii=False)[:200])
