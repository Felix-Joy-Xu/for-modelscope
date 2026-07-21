import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""测试令牌 + 探测模型列表 API 返回结构"""
import requests, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Referer': 'https://www.modelscope.cn/',
})

token = MODELSCOPE_TOKEN
s.headers['Authorization'] = token

print('=== 测试令牌 ===')
body = {'PageNumber': 1, 'PageSize': 3}
r = s.post('https://www.modelscope.cn/api/v1/models', json=body, timeout=15)
d = r.json()
print(f'status={r.status_code} code={d.get("Code")} success={d.get("Success")}')

if d.get('Data') and isinstance(d['Data'], dict):
    dd = d['Data']
    print(f'\nData keys: {list(dd.keys())[:15]}')
    print(f'TotalCount: {dd.get("TotalCount")}')
    models = dd.get('Models') or dd.get('ModelList') or []
    print(f'Models in this page: {len(models)}')
    if models:
        m = models[0]
        print(f'\nFirst model keys: {list(m.keys())}')
        for k, v in m.items():
            if isinstance(v, str):
                print(f'  {k}: {v[:80]}')
            elif isinstance(v, (int, float, bool)):
                print(f'  {k}: {v}')
            elif isinstance(v, dict):
                print(f'  {k}: dict({list(v.keys())[:6]})')
            elif isinstance(v, list):
                print(f'  {k}: list({len(v)})')
            else:
                print(f'  {k}: {type(v).__name__}')

if d.get('TotalCount'):
    print(f'\nPageNumber/Total online: TotalCount={d.get("TotalCount")}')