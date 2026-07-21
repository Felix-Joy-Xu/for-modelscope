import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""用SDK按组织列模型 + 测试数据集全量"""
import os, json
os.environ['MODELSCOPE_API_TOKEN'] = MODELSCOPE_TOKEN
from modelscope.hub.api import HubApi
api = HubApi()

# 测试 list_models 指定 owner
print('=== list_models(owner=qwen) ===')
r = api.list_models(owner_or_group='qwen', page_size=5, page_number=1)
print('Type:', type(r).__name__)
print('Keys:', list(r.keys()) if isinstance(r, dict) else 'not dict')
if isinstance(r, dict):
    for k, v in r.items():
        if isinstance(v, list):
            print(f'  {k}: list of {len(v)}')
            if v:
                first = v[0]
                if hasattr(first, 'to_dict'):
                    print(f'    first item dict keys: {list(first.to_dict().keys())[:15]}')
                elif isinstance(first, dict):
                    print(f'    first dict keys: {list(first.keys())[:15]}')
        elif isinstance(v, (int, float, str, bool)):
            print(f'  {k}: {v}')
        else:
            print(f'  {k}: {type(v).__name__}')

print()
print('=== 各组织的模型数 ===')
for org in ['qwen', 'deepseek-ai', 'ZhipuAI', 'AI-ModelScope', 'damo',
            'alibaba-pai', 'Tencent-Hunyuan', 'iic']:
    try:
        r = api.list_models(owner_or_group=org, page_size=1, page_number=1)
        tc = r.total_count if hasattr(r, 'total_count') else '?'
        print(f'  {org}: {tc} models')
    except Exception as e:
        print(f'  {org}: ERR {str(e)[:50]}')