"""探索魔搭 dolphin API——未登录下的真实模型查询接口"""
import requests, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.modelscope.cn/models',
    'x-modelscope-accept-language': 'zh_CN',
})

# 先访问首页获取CSRF cookie
r = s.get('https://www.modelscope.cn/models', timeout=15)
print("CSRF cookies:", {k: v[:30] for k, v in s.cookies.items()})

# 提取csrf_token
csrf = s.cookies.get('csrf_token', '').replace('%3D', '=')

# 然后调用 dolphin API
apis = [
    ('dolphin/model/query GET', 'GET', 'https://www.modelscope.cn/api/v1/dolphin/model/query', None),
    ('dolphin/agg/query GET', 'GET', 'https://www.modelscope.cn/api/v1/dolphin/agg/query', None),
    ('models/orgTags GET', 'GET', 'https://www.modelscope.cn/api/v1/models/orgTags?PageSize=12&PageNumber=1', None),
]

for label, method, url, body in apis:
    headers = {'x-csrf-token': csrf} if csrf else {}
    try:
        if method == 'GET':
            r = s.get(url, headers=headers, timeout=15)
        else:
            r = s.post(url, json=body, headers=headers, timeout=15)
        ct = r.headers.get('content-type', '')
        print(f"\n{label}: status={r.status_code} json={'json' in ct}")
        if r.status_code == 200 and 'json' in ct:
            d = r.json()
            print(f"  keys: {list(d.keys())[:8]}")
            if d.get('Data'):
                dd = d['Data']
                if isinstance(dd, dict):
                    print(f"  Data keys: {list(dd.keys())[:12]}")
                    print(f"  TotalCount: {dd.get('TotalCount')}")
                    # 找模型列表
                    for k in ['Models', 'ModelList', 'modelList', 'list', 'models', 'Records']:
                        if k in dd:
                            lst = dd[k]
                            print(f"  {k}: {len(lst) if isinstance(lst, list) else lst}")
                            if isinstance(lst, list) and lst:
                                print(f"  First item keys: {list(lst[0].keys())[:20]}")
                                break
    except Exception as e:
        print(f"  ERR: {str(e)[:80]}")

# 试试 PUT dolphin/modelsWithCollections（前端确实用PUT到了它）
print("\n=== dolphin/modelsWithCollections (PUT) ===")
if csrf:
    r = s.put('https://www.modelscope.cn/api/v1/dolphin/modelsWithCollections',
              headers={'x-csrf-token': csrf},
              json={},
              timeout=15)
    print(f"  PUT status={r.status_code} body={r.text[:200]}")

# 直接尝试分页的 dolphin/model/query
print("\n=== dolphin/model/query with params ===")
params_list = [
    {'PageNumber': 1, 'PageSize': 5},
    {'pageNumber': 1, 'pageSize': 5},
    {'PageNumber': 1, 'PageSize': 5, 'SortBy': 'Default'},
]
for params in params_list:
    r = s.get('https://www.modelscope.cn/api/v1/dolphin/model/query',
              params=params, headers={'x-csrf-token': csrf}, timeout=15)
    if r.status_code == 200:
        d = r.json()
        if d.get('Data'):
            dd = d['Data']
            if isinstance(dd, dict):
                tc = dd.get('TotalCount')
                models = dd.get('Models', [])
                print(f"  {params}: TC={tc} models={len(models)}")
                if models:
                    print(f"    keys: {list(models[0].keys())[:15]}")