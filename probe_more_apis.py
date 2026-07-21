import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""尝试更多 API 端点和搜索方式"""
import requests, json

TOKEN = MODELSCOPE_TOKEN
s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.modelscope.cn/models",
})
s.get("https://www.modelscope.cn/models", timeout=30)
s.cookies.set("token", TOKEN, domain="modelscope.cn")
s.cookies.set("ms_token", TOKEN, domain="modelscope.cn")

# 尝试搜索 API
print("=== 搜索 API ===")
search_apis = [
    ("PUT dolphin/search", "/api/v1/dolphin/search", {"Key": "AI", "PageSize": 5, "PageNumber": 1}),
    ("PUT dolphin/searchModels", "/api/v1/dolphin/searchModels", {"Key": "AI", "PageSize": 5}),
    ("POST models/search", "/api/v1/models/search", {"Key": "AI", "PageSize": 5, "PageNumber": 1}),
    ("PUT dolphin/model/search", "/api/v1/dolphin/model/search", {"Key": "AI", "PageSize": 5}),
    ("GET dolphin/search", "/api/v1/dolphin/search?Key=AI&PageSize=5", None),
]
for label, path, body in search_apis:
    url = f"https://www.modelscope.cn{path}"
    try:
        if body is None:
            r = s.get(url, timeout=10)
        else:
            r = s.put(url, json=body, timeout=10) if "PUT" in label else s.post(url, json=body, timeout=10)
        if r.status_code == 200:
            d = r.json()
            print(f"  [{r.status_code}] {label}: code={d.get('Code')} keys={list(d.get('Data',{}).keys())[:6] if isinstance(d.get('Data'),dict) else 'list'}")
        else:
            print(f"  [{r.status_code}] {label}")
    except Exception as e:
        print(f"  ERR {label}: {str(e)[:50]}")

# 尝试 models API 带 token 不同格式
print("\n=== /api/v1/models POST (各种认证) ===")
auth_variations = [
    {"headers": {"Authorization": TOKEN}, "body": {"PageNumber": 1, "PageSize": 5}},
    {"headers": {"Authorization": f"Bearer {TOKEN}"}, "body": {"PageNumber": 1, "PageSize": 5}},
    {"headers": {"token": TOKEN}, "body": {"PageNumber": 1, "PageSize": 5}},
    {"headers": {"X-ModelScope-Token": TOKEN}, "body": {"PageNumber": 1, "PageSize": 5}},
    {"headers": {}, "body": {"PageNumber": 1, "PageSize": 5, "Token": TOKEN}},
    {"headers": {}, "body": {"PageNumber": 1, "PageSize": 5, "AccessToken": TOKEN}},
]
for v in auth_variations:
    r = s.post("https://www.modelscope.cn/api/v1/models", 
               headers=v["headers"], json=v["body"], timeout=10)
    if r.status_code == 200:
        d = r.json()
        print(f"  OK: {v['headers']} TC={d.get('Data',{}).get('TotalCount','?')}")
    else:
        d = r.json() if r.headers.get('content-type','').startswith('application/json') else {}
        print(f"  [{r.status_code}] {list(v['headers'].keys())} msg={d.get('Message','')[:40]}")

# 尝试用 SDK 端点（modelscope package 用的）
print("\n=== SDK 风格端点 ===")
sdk_apis = [
    ("POST hub/listModels", "/api/v1/hub/listModels", {"PageNumber": 1, "PageSize": 5}),
    ("GET hub/models", "/api/v1/hub/models", None),
    ("POST models/list", "/api/v1/models/list", {"PageNumber": 1, "PageSize": 5}),
    ("POST dolphin/models", "/api/v1/dolphin/models", {"PageSize": 5, "PageNumber": 1}),
    ("POST mymodels", "/api/v1/mymodels", {"PageNumber": 1, "PageSize": 5}),
]
for label, path, body in sdk_apis:
    url = f"https://www.modelscope.cn{path}"
    try:
        if body is None:
            r = s.get(url, timeout=10)
        else:
            r = s.post(url, json=body, timeout=10)
        if r.status_code == 200:
            d = r.json()
            print(f"  [{r.status_code}] {label}: code={d.get('Code')}")
            if d.get('Data'):
                dd = d['Data']
                if isinstance(dd, dict):
                    print(f"    keys={list(dd.keys())[:8]} TC={dd.get('TotalCount','?')}")
        else:
            print(f"  [{r.status_code}] {label}")
    except Exception as e:
        print(f"  ERR {label}: {str(e)[:50]}")