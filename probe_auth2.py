"""拦截魔搭前端实际网络请求，找到 API 认证方式"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    api_calls = []
    def on_req(req):
        url = req.url
        if "/api/" in url and not url.endswith(".js") and not url.endswith(".css") and not url.endswith(".png"):
            headers = dict(req.headers)
            token_info = {}
            for k, v in headers.items():
                if k.lower() in ["authorization", "token", "x-token", "x-md-token", "x-csrf-token", "cookie"]:
                    token_info[k] = v[:50]
            api_calls.append({"method": req.method, "url": url[:100], "token_info": token_info})
    page.on("request", on_req)

    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(10000)
    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(5000)

    print("拦截到 " + str(len(api_calls)) + " 个 API 请求")
    for c in api_calls[:30]:
        ti = c.get("token_info", {})
        ti_str = json.dumps(ti, ensure_ascii=False) if ti else "(no token header)"
        path = c["url"]
        path_part = path.split("/api/v1/")[-1] if "/api/v1/" in path else path.split("/api/")[-1]
        print(c["method"] + " " + path_part[:60] + " " + ti_str[:70])

    # 分析 cookie
    print("\n=== Cookie ===")
    cookies = context.cookies("https://www.modelscope.cn")
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        domain = c.get("domain", "")
        if any(k in name.lower() for k in ["token", "auth", "session", "csrf", "_xsrf"]):
            print(f"  {name}: {value[:50]} | domain={domain}")
    if not any("token" in c.get("name","").lower() for c in cookies):
        print("  (无 token 相关 cookie)")

    # 查看请求里实际的关键header（全部都看）
    print("\n=== 第一个 POST 请求的全部header ===")
    for c in api_calls:
        if c["method"] == "POST":
            # 这个不够，要再拦截一次拿完整header
            break

    # 拦截完整header
    full_headers = {}
    def on_req2(req):
        if "/api/v1/models" in req.url:
            full_headers.update(dict(req.headers))
            full_headers["_method"] = req.method
            full_headers["_url"] = req.url
    page2 = context.new_page()
    page2.on("request", on_req2)
    page2.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page2.wait_for_timeout(10000)

    if full_headers:
        print("=== models API 完整header ===")
        for k, v in sorted(full_headers.items()):
            if k.startswith("_"):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v[:80]}")
    else:
        print("未拦截到 models API POST 请求")
        # 找其他POST请求的header
        print("查看其他认证相关API:")
        for c in api_calls:
            if c["method"] == "POST" and c.get("token_info"):
                print(json.dumps(c, ensure_ascii=False))

    browser.close()