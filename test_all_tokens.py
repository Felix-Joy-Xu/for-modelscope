import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""测试所有令牌"""
import requests, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Referer': 'https://www.modelscope.cn/',
})

tokens = [
    MODELSCOPE_TOKEN,
    MODELSCOPE_TOKENS[1],
    MODELSCOPE_TOKENS[2],
    MODELSCOPE_TOKENS[3],
    MODELSCOPE_TOKENS[4],
    MODELSCOPE_TOKENS[5],
    MODELSCOPE_TOKENS[6],
]

# 也试试不同的 Auth header 格式
auth_formats = [
    lambda t: t,                    # 直接 token
    lambda t: f'Bearer {t}',        # Bearer
    lambda t: f'token {t}',         # token
]

for token in tokens:
    for i, fmt in enumerate(auth_formats):
        s.headers['Authorization'] = fmt(token)
        body = {'PageNumber': 1, 'PageSize': 2}
        r = s.post('https://www.modelscope.cn/api/v1/models', json=body, timeout=10)
        d = r.json()
        if d.get('Success') or d.get('Code') == 200:
            data = d.get('Data', {})
            tc = data.get('TotalCount', '?')
            models = data.get('Models', [])
            tag = ['raw', 'Bearer', 'token'][i]
            print(f'[OK] {token[:20]}... ({tag}) TC={tc} models={len(models)}')
            if models:
                print(f'  First: {list(models[0].keys())[:15]}')
            break
        if r.status_code != 401:
            print(f'[{r.status_code}] {token[:20]}... msg={d.get("Message","")[:30]}')

# 也试试 GET 方式
print('\n=== GET with token ===')
s.headers['Authorization'] = tokens[0]
r = s.get('https://www.modelscope.cn/api/v1/models?PageNumber=1&PageSize=2', timeout=10)
print(f'  GET status={r.status_code} body={r.text[:200]}')