"""拦截魔搭 models 页面渲染时所有API请求，找到真正的模型列表API"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    # 拦截所有请求的完整信息
    all_reqs = []
    def on_req(req):
        url = req.url
        if "/api/" in url or "/dolphin/" in url:
            post_data = None
            try:
                post_data = req.post_data
            except:
                pass
            all_reqs.append({
                "method": req.method,
                "url": url[:200],
                "post_data": post_data[:500] if post_data else None,
            })

    page.on("request", on_req)

    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(10000)

    # 模拟点击"下一页"或者修改排序方式，触发模型列表加载
    print(f"拦截到 {len(all_reqs)} 个 API 请求\n")

    # 按URL分组统计
    from collections import Counter
    url_counter = Counter()
    for r in all_reqs:
        # 去掉query参数
        base_url = r["url"].split("?")[0]
        url_counter[base_url] += 1
    print("=== API 调用统计 ===")
    for url, count in url_counter.most_common(20):
        # 找匹配的方法
        methods = [r["method"] for r in all_reqs if r["url"].split("?")[0] == url]
        print(f"  {methods[0]:5s} x{count:3d}  {url[45:120]}")

    # 找包含大量返回的API
    print("\n=== 拦截响应（检查大的JSON响应） ===")
    all_resps = []
    def on_resp(resp):
        url = resp.url
        if "/api/" in url or "/dolphin/" in url:
            try:
                body = resp.text()
                if body and len(body) > 500:
                    all_resps.append({
                        "url": url[:200],
                        "status": resp.status,
                        "body_len": len(body),
                        "body_preview": body[:400],
                    })
            except:
                pass
    page2 = context.new_page()
    page2.on("response", on_resp)
    page2.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    # 等加载
    page2.wait_for_timeout(10000)
    # 滚动触发更多
    page2.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page2.wait_for_timeout(5000)

    print(f"\n拦截到 {len(all_resps)} 个大的API响应:")
    for r in sorted(all_resps, key=lambda x: -x["body_len"])[:10]:
        print(f"\n  [{r['status']}] {r['body_len']:>8} bytes  {r['url'][45:120]}")
        print(f"    preview: {r['body_preview'][:250]}")