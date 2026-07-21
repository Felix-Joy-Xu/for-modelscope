"""直接调用 dolphin/modelsWithCollections API 分页拉取全部模型"""
import requests, json

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://www.modelscope.cn/models',
    'x-modelscope-accept-language': 'zh_CN',
})

# 先访问首页拿 csrf_token cookie
r = s.get('https://www.modelscope.cn/models', timeout=15)
csrf = s.cookies.get('csrf_token', '').replace('%3D', '=')
print(f"csrf_token: {csrf}")

# 调用 dolphin/modelsWithCollections
print('\n=== PUT dolphin/modelsWithCollections ===')
r = s.put('https://www.modelscope.cn/api/v1/dolphin/modelsWithCollections',
          headers={'x-csrf-token': csrf},
          json={'PageSize': 5, 'PageNumber': 1},
          timeout=15)
print(f'Status: {r.status_code}')
d = r.json()
print(f'Code: {d.get("Code")} Success: {d.get("Success")}')

data = d.get('Data', {})
print(f'Data keys: {list(data.keys())[:15]}')
print(f'TotalCount: {data.get("TotalCount")}')

# 找模型列表
for k in data.keys():
    v = data[k]
    if isinstance(v, list) and len(v) > 0:
        print(f'\n{k}: list of {len(v)}')
        if isinstance(v[0], dict):
            print(f'  First item keys: {list(v[0].keys())[:20]}')
            item = v[0]
            for ik, iv in item.items():
                if isinstance(iv, str):
                    print(f'    {ik}: {iv[:60]}')
                elif isinstance(iv, (int, float, bool)):
                    print(f'    {ik}: {iv}')
                elif isinstance(iv, dict):
                    print(f'    {ik}: dict({list(iv.keys())[:5]})')
                elif isinstance(iv, list):
                    print(f'    {ik}: list({len(iv)})')

# 保存响应样本
with open('modelscope_output/_dolphin_p1_sample.json', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print('\n样本已保存到 _dolphin_p1_sample.json')