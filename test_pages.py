"""测试 dolphin 分页，结构更稳健"""
import requests, json

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.modelscope.cn/models",
})

for p in [1, 5, 20, 100, 500, 1000]:
    r = s.put("https://www.modelscope.cn/api/v1/dolphin/modelsWithCollections",
              json={"PageSize": 100, "PageNumber": p}, timeout=15)
    d = r.json()
    items = d["Data"]["ModelCollection"]
    valid_items = [i for i in items if isinstance(i, dict) and i.get("Collection")]
    valid_colls = [i["Collection"] for i in valid_items]
    valid = sum(1 for c in valid_colls if c.get("Name") or c.get("Path"))
    names = [c.get("Name", "") or c.get("Path", "") for c in valid_colls]
    print(f"Page {p}: {len(items)} items, {len(valid_items)} with Collection, {valid} with name/path, first={names[0][:30] if names else 'none'}")

total = d["Data"]["TotalCount"]
valid_in_page = len(valid_items)
ratio = valid_in_page / len(items) if items else 0
est = int(ratio * total)
print(f"\nTotalCount: {total:,}")
print(f"Ratio: {valid_in_page}/{len(items)} = {ratio:.3f}")
print(f"Estimated valid: ~{est:,}")
print(f"Pages needed: ~{max(est // 100, 1000)}")
