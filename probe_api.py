"""探测魔搭的模型/数据集/创空间列表 API"""
import requests, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Referer': 'https://www.modelscope.cn/',
})

def probe(label, url, **kwargs):
    try:
        r = s.get(url, timeout=10, **kwargs)
        ct = r.headers.get('content-type', '')
        is_json = 'json' in ct
        print(f'  [{r.status_code}] {label}: json={is_json}')
        if r.status_code == 200 and is_json:
            d = r.json()
            if isinstance(d, dict):
                print(f'    top keys: {list(d.keys())[:8]}')
                data = d.get('Data') or d.get('data')
                if isinstance(data, dict):
                    print(f'    Data keys: {list(data.keys())[:10]}')
                    for k in ['Models', 'modelList', 'List', 'models', 'TotalCount', 'Total', 'Studios']:
                        if k in data:
                            v = data[k]
                            n = len(v) if isinstance(v, list) else v
                            print(f'      {k}: {n}')
                elif isinstance(data, list):
                    print(f'    Data is list of {len(data)}')
    except Exception as e:
        print(f'  [ERR] {label}: {str(e)[:80]}')

print('=== Models API ===')
probe('models', 'https://www.modelscope.cn/api/v1/models')
probe('models?page=1&size=5', 'https://www.modelscope.cn/api/v1/models?page=1&size=5')
probe('models/list', 'https://www.modelscope.cn/api/v1/models/list')
probe('models?PageSize=5', 'https://www.modelscope.cn/api/v1/models?PageSize=5&PageNumber=1')

print('\n=== Datasets API ===')
probe('datasets', 'https://www.modelscope.cn/api/v1/datasets')
probe('datasets/list', 'https://www.modelscope.cn/api/v1/datasets/list')
probe('datasets?page=1&size=5', 'https://www.modelscope.cn/api/v1/datasets?page=1&size=5')

print('\n=== Studios API ===')
probe('studios', 'https://www.modelscope.cn/api/v1/studios')
probe('studios Beta', 'https://www.modelscope.cn/api/v1/studios_beta')
probe('studios/list', 'https://www.modelscope.cn/api/v1/studios/list')
probe('studios?page=1&size=5', 'https://www.modelscope.cn/api/v1/studios?page=1&size=5')

# 尝试 POST 方式（很多 API 需要 POST）
print('\n=== POST Models ===')
for body in [
    {'PageNumber': 1, 'PageSize': 5},
    {'PageSize': 5, 'PageNumber': 1, 'SortBy': 'Default'},
    {'limit': 5, 'offset': 0},
]:
    r = s.post('https://www.modelscope.cn/api/v1/models', json=body, timeout=10)
    if r.status_code == 200:
        d = r.json()
        print(f'  POST {body}: keys={list(d.keys())[:6]}')
        if 'Data' in d and isinstance(d['Data'], dict):
            print(f'    Data keys: {list(d["Data"].keys())[:10]}')
            for k in ['Models', 'TotalCount']:
                if k in d['Data']:
                    v = d['Data'][k]
                    print(f'    {k}: {len(v) if isinstance(v, list) else v}')

print('\n=== POST Datasets ===')
r = s.post('https://www.modelscope.cn/api/v1/datasets', json={'PageNumber': 1, 'PageSize': 5}, timeout=10)
if r.status_code == 200:
    d = r.json()
    print(f'  keys: {list(d.keys())[:6]}')
    if 'Data' in d and isinstance(d['Data'], dict):
        print(f'    Data keys: {list(d["Data"].keys())[:10]}')

print('\n=== POST Studios ===')
r = s.post('https://www.modelscope.cn/api/v1/studios', json={'PageNumber': 1, 'PageSize': 5}, timeout=10)
if r.status_code == 200:
    d = r.json()
    print(f'  keys: {list(d.keys())[:6]}')
    if 'Data' in d and isinstance(d['Data'], dict):
        print(f'    Data keys: {list(d["Data"].keys())[:10]}')