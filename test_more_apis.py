"""查找 models/datasets/studios 各自的列表 API"""
import requests, json

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.modelscope.cn/models",
})

# 获取 CSRF
r = s.get("https://www.modelscope.cn/models", timeout=15)
csrf = s.cookies.get("csrf_token", "").replace("%3D", "=")

# 尝试各种 dolphin API 组合
tests = [
    ("PUT modelsWithCollections (Type=Model)", "PUT",
     "/api/v1/dolphin/modelsWithCollections",
     {"PageSize": 3, "PageNumber": 1, "Type": "Model"}),
    ("PUT modelsWithCollections (Type=Dataset)", "PUT",
     "/api/v1/dolphin/modelsWithCollections",
     {"PageSize": 3, "PageNumber": 1, "Type": "Dataset"}),
    ("POST modelsByType", "POST",
     "/api/v1/dolphin/modelsByType",
     {"PageSize": 3, "PageNumber": 1, "Business": "model"}),
    ("GET dolphin/model/list", "GET",
     "/api/v1/dolphin/model/list", None),
    ("PUT dolphin/searchModels", "PUT",
     "/api/v1/dolphin/searchModels",
     {"PageSize": 3, "PageNumber": 1}),
    ("PUT dolphin/queryModels", "PUT",
     "/api/v1/dolphin/queryModels",
     {"PageSize": 3, "PageNumber": 1}),
    ("GET model-studio list", "GET",
     "/api/v1/dolphin/model-studio/list", None),
]

for label, method, path, body in tests:
    url = f"https://www.modelscope.cn{path}"
    try:
        if method == "GET":
            r = s.get(url, headers={"x-csrf-token": csrf}, timeout=10)
        elif method == "PUT":
            r = s.put(url, headers={"x-csrf-token": csrf}, json=body, timeout=10)
        else:
            r = s.post(url, headers={"x-csrf-token": csrf}, json=body, timeout=10)
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            d = r.json()
            dd = d.get("Data", {}) or {}
            tc = dd.get("TotalCount", dd.get("Total", "?"))
            # 找列表字段
            lists = []
            if isinstance(dd, dict):
                for k, v in dd.items():
                    if isinstance(v, list) and len(v) > 0:
                        lists.append(f"{k}({len(v)})")
            print(f"[{r.status_code}] {label}: TC={tc} lists={lists}")
        else:
            print(f"[{r.status_code}] {label}")
    except Exception as e:
        print(f"[ERR] {label}: {str(e)[:50]}")

# 也查看页面 HTML 中的初始化数据
print("\n=== 页面 INITIAL STATE ===")
import re
r = s.get("https://www.modelscope.cn/models", timeout=15)
for pattern in [r"window\.__INITIAL_STATE__", r"window\.__PRELOADED_STATE__",
                r"window\.__g_initialState__", r"__DATA__\s*=",
                r"preloadData\s*=\s*", r"__NEXT_DATA__"]:
    if re.search(pattern, r.text):
        print(f"  找到: {pattern}")
        m = re.search(pattern + r"\s*=\s*(\{.*?\});", r.text, re.DOTALL)
        if m:
            raw = m.group(1)
            try:
                data = json.loads(raw)
                keys = list(data.keys())[:10]
                print(f"    keys: {keys}")
            except:
                print(f"    raw: {raw[:150]}")
