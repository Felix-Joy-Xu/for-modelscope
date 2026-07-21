import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""获取模型文件列表 + 用 raw API 拉 README"""
import os
os.environ["MODELSCOPE_API_TOKEN"] = MODELSCOPE_TOKEN
from modelscope.hub.api import HubApi
import requests

api = HubApi()

# 1. 用 SDK 获取文件列表
print("=== get_model_files ===")
files = api.get_model_files("qwen/Qwen2.5-7B-Instruct")
readme_files = []
for f in files:
    name = f.path if hasattr(f, "path") else str(f)
    if "readme" in name.lower() or "model_card" in name.lower() or name.lower().endswith(".md"):
        readme_files.append(name)
    print(f"  {name}")
print(f"\nREADME candidates: {readme_files}")

# 2. 用 raw URL 直接拉 README
print("\n=== 拉 README 全文 ===")
for url_pattern in [
    "https://www.modelscope.cn/models/qwen/Qwen2.5-7B-Instruct/resolve/master/README.md",
    "https://www.modelscope.cn/api/v1/models/qwen/Qwen2.5-7B-Instruct/repo?Revision=master&FilePath=README.md",
]:
    try:
        r = requests.get(url_pattern, timeout=15)
        print(f"  [{r.status_code}] {url_pattern[:80]}")
        if r.status_code == 200:
            print(f"  len: {len(r.text)} chars")
            print(f"  preview: {r.text[:200]}")
            break
    except Exception as e:
        print(f"  ERR: {str(e)[:50]}")