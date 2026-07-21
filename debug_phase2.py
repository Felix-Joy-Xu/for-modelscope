import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""调试 Phase 2 认证 - 直接复制脚本里的流程"""
import requests, json

BASE = "https://www.modelscope.cn"
TOKEN = MODELSCOPE_TOKEN

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": f"{BASE}/models",
})

# 模拟 _refresh_csrf
r = s.get(f"{BASE}/models", timeout=30)
print(f"GET status: {r.status_code}")
print(f"Initial cookies: {dict(s.cookies)}")

# 设置 token
s.cookies.set("token", TOKEN, domain="modelscope.cn")
s.cookies.set("ms_token", TOKEN, domain="modelscope.cn")
csrf = s.cookies.get("csrf_token", "").replace("%3D", "=")
print(f"CSRF: '{csrf}'")
print(f"All cookies after token set:")
for c in s.cookies:
    print(f"  {c.name}={c.value[:30]} domain={c.domain}")

# 直接测试分页
print("\n=== 分页测试（直接在脚本环境）===")
for p in [1, 2, 3, 4]:
    r = s.put(f"{BASE}/api/v1/dolphin/modelsWithCollections",
              json={"PageSize": 5, "PageNumber": p},
              headers={"x-csrf-token": csrf} if csrf else {},
              timeout=15)
    d = r.json()
    items = d["Data"]["ModelCollection"]
    valid = sum(1 for i in items if i.get("Collection", {}).get("Name"))
    names = [i["Collection"]["Name"][:25] for i in items if i.get("Collection", {}).get("Name")]
    print(f"Page {p}: {len(items)} items, {valid} valid, names={names[:3]}")

# 不带 csrf token 测试
print("\n=== 不带 csrf-token 测试 ===")
for p in [1, 2, 3]:
    r = s.put(f"{BASE}/api/v1/dolphin/modelsWithCollections",
              json={"PageSize": 5, "PageNumber": p},
              timeout=15)
    d = r.json()
    items = d["Data"]["ModelCollection"]
    valid = sum(1 for i in items if i.get("Collection", {}).get("Name"))
    names = [i["Collection"]["Name"][:25] for i in items if i.get("Collection", {}).get("Name")]
    print(f"Page {p}: {len(items)} items, {valid} valid, names={names[:3]}")