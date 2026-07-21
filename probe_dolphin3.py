"""分析 dolphin/modelsWithCollections API 的完整请求/响应"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    request_data = {}
    response_data = {}

    def on_req(req):
        if "modelsWithCollections" in req.url:
            try:
                pd = req.post_data
                request_data["method"] = req.method
                request_data["url"] = req.url
                request_data["post_data"] = pd
                request_data["headers"] = dict(req.headers)
            except:
                pass

    def on_resp(resp):
        if "modelsWithCollections" in resp.url:
            try:
                resp_data["url"] = resp.url
                resp_data["status"] = resp.status
                resp_data["body"] = resp.text()
            except:
                pass

    page.on("request", on_req)
    page.on("response", on_resp)

    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(15000)  # 多等点
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(5000)

    print("=== 请求信息 ===")
    print(f"  Method: {request_data.get('method')}")
    print(f"  URL: {request_data.get('url')[:120]}")
    pd = request_data.get("post_data")
    if pd:
        print(f"  Post data ({len(pd)} chars):")
        try:
            j = json.loads(pd)
            print(f"    {json.dumps(j, ensure_ascii=False, indent=2)[:600]}")
        except:
            print(f"    {pd[:500]}")

    print("\n=== 请求Headers ===")
    for k, v in request_data.get("headers", {}).items():
        if k.lower() in ["content-type", "x-csrf-token", "cookie", "referer", "accept"]:
            print(f"  {k}: {v[:80]}")

    # 解析响应
    body = resp_data.get("body", "")
    print(f"\n=== 响应 ===\n  Status: {resp_data.get('status')}\n  Body: {len(body)} bytes")

    if body:
        d = json.loads(body)
        data = d.get("Data", {})
        print(f"  Data keys: {list(data.keys())[:10]}")

        # 找模型列表
        for k in ["Models", "modelList", "ModelList", "list", "ModelsAndCollections"]:
            if k in data:
                v = data[k]
                print(f"  {k}: type={type(v).__name__}")
                if isinstance(v, list):
                    print(f"    len: {len(v)}")
                    if v and isinstance(v[0], dict):
                        print(f"    first item keys: {list(v[0].keys())[:20]}")

        # 找 totalCount
        for k in ["TotalCount", "totalCount", "Total", "total"]:
            if k in data:
                print(f"  {k}: {data[k]}")

        # 直接保存前2KB看看
        with open("modelscope_output/_dolphin_sample.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print(f"  完整响应已保存到 _dolphin_sample.json")

    browser.close()