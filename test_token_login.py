import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""用 Playwright 注入用户提供的 tokens 尝试登录态"""
from playwright.sync_api import sync_playwright
import json

tokens = [
    MODELSCOPE_TOKEN,
    MODELSCOPE_TOKENS[1],
    MODELSCOPE_TOKENS[2],
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    for token in tokens[:1]:  # 测试第一个
        context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # 方法1: 注入 token 到 localStorage
        page.goto("https://www.modelscope.cn", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # 设置 token
        page.evaluate(f"""() => {{
            localStorage.setItem('token', '{token}');
            localStorage.setItem('ms_token', '{token}');
            localStorage.setItem('ModelScopeToken', '{token}');
        }}""")

        # 方法2: 设置 cookie
        context.add_cookies([
            {"name": "token", "value": token, "domain": ".modelscope.cn", "path": "/"},
            {"name": "ms_token", "value": token, "domain": ".modelscope.cn", "path": "/"},
            {"name": "Authorization", "value": f"Bearer {token}", "domain": ".modelscope.cn", "path": "/"},
        ])

        # 刷新
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # 检查登录状态
        login_info = page.evaluate("""async () => {
            let r = await fetch('/api/v1/users/login/info');
            return await r.json();
        }""")
        print(f"Token {token[:20]}... login/info: code={login_info.get('Code')} msg={login_info.get('Message','')[:40]}")

        # 测试模型列表 API
        api_result = page.evaluate("""async () => {
            let r = await fetch('/api/v1/models', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({PageNumber: 1, PageSize: 5})
            });
            return await r.json();
        }""")
        print(f"  POST models: code={api_result.get('Code')}")
        if api_result.get('Data'):
            dd = api_result['Data']
            print(f"  TC={dd.get('TotalCount')} keys={list(dd.keys())[:8]}")

        # 确认模型列表是否真实分页
        api_p2 = page.evaluate("""async () => {
            let r = await fetch('/api/v1/models', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({PageNumber: 2, PageSize: 5})
            });
            return await r.json();
        }""")
        print(f"  POST models(page2): code={api_p2.get('Code')}")

        # 也试试 dolphin API 大页码
        api_dolphin = page.evaluate("""async () => {
            let r = await fetch('/api/v1/dolphin/modelsWithCollections', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({PageNumber: 2, PageSize: 3})
            });
            return await r.json();
        }""")
        print(f"  PUT dolphin(p2): code={api_dolphin.get('Code')} TC={api_dolphin.get('Data',{}).get('TotalCount','?')}")
        items = api_dolphin.get("Data", {}).get("ModelCollection", [])
        print(f"  Items: {len(items)}")
        if items:
            names = [i.get("Collection", {}).get("Name", "") for i in items if i.get("Collection", {}).get("Name")]
            print(f"  Names: {names[:3]}")

        context.close()

    browser.close()