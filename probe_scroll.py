"""无限滚动模型页面，拦截API获取真实模型分页接口"""
from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    responses = []
    def on_resp(resp):
        url = resp.url
        if "/api/" in url and resp.status == 200:
            try:
                body = resp.text()
                if body and len(body) > 500 and "model" in url.lower():
                    responses.append({"url": url, "method": resp.request.method,
                                      "len": len(body), "body": body[:300]})
            except:
                pass

    page.on("response", on_resp)

    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(8000)
    # 初始API响应
    print(f"初始拦截: {len(responses)} 个")

    # 模拟滚动30次
    for i in range(30):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

    new_resps = [r for r in responses if r not in responses[:len(responses)-len(responses)//2]]
    print(f"最终拦截: {len(responses)} 个")

    # 找POST/PUT请求，看body
    print("\n=== POST/PUT 请求 ===")
    all_reqs = []
    def on_req(req):
        if "/api/" in req.url and req.method in ["POST", "PUT"] and "model" in req.url.lower():
            try:
                all_reqs.append({"url": req.url, "method": req.method, "post": req.post_data})
            except:
                pass
    page2 = context.new_page()
    page2.on("request", on_req)
    page2.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page2.wait_for_timeout(8000)
    for j in range(10):
        page2.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page2.wait_for_timeout(3000)

    print(f"\n拦截到 {len(all_reqs)} 个模型相关POST/PUT请求:")
    for r in all_reqs[:10]:
        print(f"  {r['method']} {r['url'][:120]}")
        print(f"    body: {r.get('post', 'N/A')[:150]}")
    print(f"  ... 共 {len(all_reqs)} 个")

    browser.close()