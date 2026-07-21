"""调试：创空间页面渲染检查"""
from playwright.sync_api import sync_playwright
import os

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    # 尝试路径1: studios_beta
    print("=== 尝试1: /studios_beta ===")
    try:
        page.goto("https://www.modelscope.cn/studios_beta", wait_until="load", timeout=30000)
    except:
        pass
    page.wait_for_timeout(8000)
    links = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href)
            .filter(h => h.includes('studios') && !h.includes('javascript'));
    }""")
    print(f"  含 'studios' 的链接数: {len(links)}")
    for l in links[:8]:
        print(f"    {l}")

    # body 文本
    body_text = page.evaluate("() => document.body?.innerText || ''")
    print(f"  Body 文本字数: {len(body_text)}")
    if len(body_text) < 500:
        print(f"  text: {body_text[:200]}")

    # 尝试路径2: /studios
    print("\n=== 尝试2: /studios ===")
    page.goto("https://www.modelscope.cn/studios", wait_until="load", timeout=30000)
    page.wait_for_timeout(8000)
    links2 = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href)
            .filter(h => h.includes('studios'));
    }""")
    print(f"  链接数: {len(links2)}")
    for l in links2[:5]:
        print(f"    {l}")

    # 拦截 API
    print("\n=== 拦截 API 调用 ===")
    api_calls = []
    def on_resp(resp):
        if "/api/" in resp.url and resp.status == 200:
            try:
                body = resp.text()
                if body and len(body) > 200:
                    api_calls.append({"url": resp.url[:120], "len": len(body)})
            except:
                pass
    page.on("response", on_resp)
    page.goto("https://www.modelscope.cn/studios_beta", wait_until="load", timeout=30000)
    page.wait_for_timeout(10000)
    print(f"  API 调用: {len(api_calls)} 个")
    for c in sorted(api_calls, key=lambda x: -x['len'])[:5]:
        print(f"    {c['len']:>7}b  {c['url']}")

    browser.close()