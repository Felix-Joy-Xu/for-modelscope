import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""提取 Playwright 有效认证信息，用于 requests"""
from playwright.sync_api import sync_playwright
import json

TOKEN = MODELSCOPE_TOKEN

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    for attempt in range(3):
        try:
            page.goto("https://www.modelscope.cn/models", wait_until="load", timeout=30000)
            break
        except:
            print(f"  Retry {attempt+1}...")
            page.wait_for_timeout(3000)

    page.wait_for_timeout(8000)

    # 注入 token
    page.evaluate(f"""() => {{
        localStorage.setItem('token', '{TOKEN}');
        localStorage.setItem('ms_token', '{TOKEN}');
    }}""")
    context.add_cookies([
        {"name": "token", "value": TOKEN, "domain": ".modelscope.cn", "path": "/"},
        {"name": "ms_token", "value": TOKEN, "domain": ".modelscope.cn", "path": "/"},
    ])

    # 提取实际 cookie（包括 csrf）
    cookies = context.cookies()
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    print("=== Cookie string for requests ===")
    print(f"'Cookie': '{cookie_str[:100]}...'")
    print()

    # 测试：用页面内fetch验证分页
    print("=== 验证分页 ===")
    for p in [1, 2, 3, 4, 5]:
        result = page.evaluate(f"""async () => {{
            let r = await fetch('/api/v1/dolphin/modelsWithCollections', {{
                method: 'PUT',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{PageNumber: {p}, PageSize: 30}})
            }});
            return await r.json();
        }}""")
        items = result["Data"]["ModelCollection"]
        valid = sum(1 for i in items if i.get("Collection", {}).get("Name"))
        names = [i["Collection"]["Name"][:25] for i in items if i.get("Collection", {}).get("Name")]
        print(f"  Page {p}: {len(items)} items, {valid} valid, names={names[:3]}")

    # 保存 cookie 到文件，供 requests 爬虫用
    print(f"\n=== 保存认证文件 ===")
    with open("modelscope_output/_playwright_cookies.json", "w") as f:
        json.dump(list(cookies), f, indent=2)
    print(f"  cookies saved ({len(cookies)} cookies)")

    browser.close()