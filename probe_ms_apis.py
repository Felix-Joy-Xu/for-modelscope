import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

import requests
import json

TOKEN = MODELSCOPE_TOKEN # Got from previous files
s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Cookie": f"token={TOKEN}; ms_token={TOKEN}"
})

print("=== 1. Native Comments API ===")
# Try different paths for comments
urls = [
    "https://www.modelscope.cn/api/v1/models/qwen/Qwen2.5-7B-Instruct/comments",
    "https://www.modelscope.cn/api/v1/comments?TargetId=qwen/Qwen2.5-7B-Instruct&TargetType=model",
    "https://www.modelscope.cn/api/v1/discussions?TargetId=qwen/Qwen2.5-7B-Instruct&TargetType=model"
]
for u in urls:
    r = s.get(u, timeout=5)
    print(f"[{r.status_code}] {u}")
    if r.status_code == 200: print(" -> OK keys:", list(r.json().get('Data',{}).keys())[:5] if isinstance(r.json().get('Data'), dict) else "List")

print("\n=== 2. Commit History / Branches ===")
url = "https://www.modelscope.cn/api/v1/models/qwen/Qwen2.5-7B-Instruct/branches"
r = s.get(url, timeout=5)
print(f"[{r.status_code}] {url}")
if r.status_code == 200: print(" -> OK keys:", list(r.json().get('Data',{}).keys())[:5] if isinstance(r.json().get('Data'), dict) else "List/Data")

url = "https://www.modelscope.cn/api/v1/models/qwen/Qwen2.5-7B-Instruct/revisions"
r = s.get(url, timeout=5)
print(f"[{r.status_code}] {url}")

print("\n=== 3. User Profiles ===")
url = "https://www.modelscope.cn/api/v1/users/Qwen"
r = s.get(url, timeout=5)
print(f"[{r.status_code}] {url}")
if r.status_code == 200: print(" -> OK keys:", list(r.json().get('Data',{}).keys())[:5] if isinstance(r.json().get('Data'), dict) else "List/Data")

print("\n=== 4. File Trees ===")
url = "https://www.modelscope.cn/api/v1/models/qwen/Qwen2.5-7B-Instruct/repo/tree?Revision=master"
r = s.get(url, timeout=5)
print(f"[{r.status_code}] {url}")
if r.status_code == 200: print(" -> OK")

print("\n=== 5. Leaderboards ===")
url = "https://www.modelscope.cn/api/v1/leaderboard"
r = s.get(url, timeout=5)
print(f"[{r.status_code}] {url}")
