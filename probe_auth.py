import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""探索魔搭认证方式——用Playwright登录态注入token"""
import os, json
from playwright.sync_api import sync_playwright

tokens = [
    MODELSCOPE_TOKEN,
    MODELSCOPE_TOKENS[1],
    MODELSCOPE_TOKENS[2],
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)

    # 查看魔搭JS实际用的认证方式
    print("=== 检查魔搭JS的认证方式 ===")

    # 方法1: 直接在页面内设置cookie后fetch
    print("\n--- 方法1: Cookie方式 ---")
    for token in tokens[:3]:
        # 设置cookie
        page.context.add_cookies([
            {"name": "ms_token", "value": token, "domain": ".modelscope.cn", "path": "/"},
            {"name": "token", "value": token, "domain": ".modelscope.cn", "path": "/"},
            {"name": "Authorization", "value": token, "domain": ".modelscope.cn", "path": "/"},
        ])

        result = page.evaluate("""async (token) => {
            // 尝试不同的header方式
            let results = {};
            for (let mode of ['header_bearer', 'header_raw', 'header_token', 'cookie_prefilled']) {
                let headers = {'Content-Type': 'application/json'};
                if (mode === 'header_bearer') headers['Authorization'] = 'Bearer ' + token;
                else if (mode === 'header_raw') headers['Authorization'] = token;
                else if (mode === 'header_token') headers['token'] = token;

                try {
                    let resp = await fetch('/api/v1/models', {
                        method: 'POST',
                        headers: headers,
                        body: JSON.stringify({PageNumber: 1, PageSize: 2}),
                    });
                    let data = await resp.json();
                    results[mode] = {
                        status: resp.status,
                        code: data.Code,
                        success: data.Success,
                        tc: data.Data ? (data.Data.TotalCount || null) : null,
                    };
                    if (data.Success) {
                        results[mode].modelKeys = data.Data.Models ? Object.keys(data.Data.Models[0]).slice(0, 15) : null;
                    }
                } catch(e) {
                    results[mode] = {error: e.message};
                }
            }
            return results;
        }""", token)

        print(f"\n  Token: {token[:20]}...")
        for mode, info in result.items():
            ok = info.get('success')
            line = f"    {mode:25s} status={info.get('status')} code={info.get('code')} success={ok}"
            if ok:
                line += f" TC={info.get('tc')} keys={info.get('modelKeys')}"
            print(line)

    # 方法2: 检查已有的API调用header格式
    print("\n=== 方法2: 拦截API请求看实际header ===")
    api_headers = []
    def on_request(req):
        if '/api/v1/models' in req.url and req.method == 'POST':
            api_headers.append(dict(req.headers))
    page.on("request", on_request)

    # 刷新页面触发新的API调用
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(2000)

    # 如果有拦截到，打印header
    if api_headers:
        print(f"  拦截到 {len(api_headers)} 个 models API 请求:")
        h = api_headers[0]
        for k, v in h.items():
            print(f"    {k}: {v[:80]}")
    else:
        print("  未拦截到 models POST 请求")

    # 直接试探页面JS已发送的请求用什么header
    print("\n=== 方法3: 拦截所有API请求看header格式 ===")
    all_headers = []
    def on_req(req):
        if '/api/' in req.url and req.method == 'POST':
            all_headers.append({'url': req.url, 'headers': dict(req.headers)})
    page2 = context.new_page()
    page2.on("request", on_req)
    page2.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page2.wait_for_timeout(8000)

    print(f"  拦截到 {len(all_headers)} 个 POST API 请求:")
    for h in all_headers[:3]:
        print(f"  URL: {h['url'][:80]}")
        for k, v in h['headers'].items():
            if k.lower() in ['authorization', 'token', 'cookie', 'x-token', 'x-csrf-token', 'x-md-token']:
                print(f"    {k}: {v[:80]}")

    browser.close()