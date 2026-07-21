"""测试 dolphin API 的过滤参数"""
import requests, json

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://www.modelscope.cn/models",
})

base_url = "https://www.modelscope.cn/api/v1/dolphin/modelsWithCollections"

# 测试不同的过滤body
tests = [
    {"PageSize": 5, "PageNumber": 1, "DomainName": "nlp"},
    {"PageSize": 5, "PageNumber": 1, "DomainName": "multi-modal"},
    {"PageSize": 5, "PageNumber": 1, "SortBy": "Downloads"},
    {"PageSize": 5, "PageNumber": 1, "SortBy": "Recent"},
    {"PageSize": 5, "PageNumber": 1, "TaskId": 22},
    {"PageSize": 5, "PageNumber": 1, "SearchQuery": "AI"},
    {"PageSize": 5, "PageNumber": 1, "License": "apache-2.0"},
    {"PageSize": 5, "PageNumber": 1, "Provider": "Alibaba"},
]

for body in tests:
    r = s.put(base_url, json=body, timeout=15)
    d = r.json()
    items = d["Data"]["ModelCollection"]
    valid = sum(1 for i in items if i.get("Collection", {}).get("Name"))
    label = "|".join(f"{k}={v}" for k, v in body.items() if k != "PageSize" and k != "PageNumber")
    print(f"[{r.status_code}] {label:45s} valid={valid}/{len(items)} TC={d['Data']['TotalCount']}")

# 也测试 POST 方式的搜索
print("\n=== Search APIs ===")
search_bodies = [
    {"SearchKey": "开源大模型", "PageSize": 5, "PageNumber": 1},
    {"SearchKey": "llm", "PageSize": 5, "PageNumber": 1},
]
for body in search_bodies:
    for path in ["/api/v1/dolphin/searchModels", "/api/v1/dolphin/model/query",
                 "/api/v1/models/search", "/api/v1/dolphin/models/search"]:
        try:
            r = s.put(f"https://www.modelscope.cn{path}", json=body, timeout=10)
            if r.status_code == 200:
                d = r.json()
                print(f"  PUT {path}: {r.status_code} TC={d.get('Data',{}).get('TotalCount','?')}")
        except:
            pass
