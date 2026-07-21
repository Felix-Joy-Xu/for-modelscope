import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

#!/usr/bin/env python3
"""补充采集：创空间（Studios）—直接用 dolphin/studios API 分页"""
import os, json, time, csv, requests

TOKEN = MODELSCOPE_TOKEN
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
API = "https://www.modelscope.cn/api/v1/dolphin/studios"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://www.modelscope.cn/studios_beta",
})
s.get("https://www.modelscope.cn/studios_beta", timeout=30)
s.cookies.set("token", TOKEN, domain="modelscope.cn")
s.cookies.set("ms_token", TOKEN, domain="modelscope.cn")

# 先用 PUT 调用看返回结构
r = s.put(API, json={"PageSize": 5, "PageNumber": 1}, timeout=15)
d = r.json()
data = d.get("Data", {})
print(f"p1: keys={list(data.keys())[:10] if isinstance(data, dict) else 'array'}")
tc = data.get("TotalCount")
print(f"TotalCount: {tc}")
items = data.get("ModelCollection") or data.get("Studios") or data.get("List") or []
print(f"items: {len(items)}, sample keys: {list(items[0].keys())[:15] if items else None}")

if not items:
    print("未拿到 items，可能字段名不一样")
    print(json.dumps(data, ensure_ascii=False)[:1000])
    exit()

# 全量分页采集
all_seen = set()
total = list()

page = 1
no_new_streak = 0
while page * 50 <= 3000:
    try:
        r = s.put(API, json={"PageSize": 50, "PageNumber": page}, timeout=15)
        d = r.json()
        items = d.get("Data", {}).get("ModelCollection") or d.get("Data", {}).get("Studios", [])
        new_count = 0
        for it in items:
            coll = it.get("Collection", it)
            sid = coll.get("Path") or coll.get("Id") or coll.get("Name")
            if sid and sid not in all_seen:
                all_seen.add(sid)
                total.append(coll)
                new_count += 1
        print(f"p{page}: +{new_count} (累计 {len(total)})")
        if new_count == 0:
            no_new_streak += 1
            if no_new_streak >= 3:
                break
        else:
            no_new_streak = 0
        page += 1
        time.sleep(0.1)
    except Exception as e:
        if "3000" in str(e):
            break
        print(f"ERR p{page}: {str(e)[:60]}")
        break

# 保存
if total:
    print(f"\n采集完成: {len(total)} 个创空间")

    def _clean(v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        if isinstance(v, (list, dict)):
            return json.dumps(v, ensure_ascii=False)
        return v

    with open(os.path.join(OUTPUT_DIR, "studios_all.json"), "w", encoding="utf-8") as f:
        json.dump([{k: _clean(v) for k, v in s.items()} for s in total],
                  f, ensure_ascii=False, indent=2)

    fields = sorted(total[0].keys())
    with open(os.path.join(OUTPUT_DIR, "studios_all.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for st in total:
            w.writerow({k: _clean(v) for k, v in st.items()})

    print(f"已保存: studios_all.json + studios_all.csv")