"""找正确的模型列表API——深入查看React状态 + 模拟分页交互"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    # 拦截所有API完整请求和响应
    api_log = []
    def on_resp(resp):
        try:
            url = resp.url
            if '/api/' in url and resp.status == 200:
                body = resp.text()
                if body and len(body) > 1000 and 'model' in body.lower():
                    # 这是大响应且可能含模型数据
                    api_log.append({
                        'url': url[:200],
                        'method': resp.request.method,
                        'body': body,
                        'len': len(body),
                    })
        except:
            pass
    page.on("response", on_resp)

    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(12000)

    # 看哪个API响应最大且包含模型id
    print(f"拦截到 {len(api_log)} 个含 model 的大API响应")
    api_log.sort(key=lambda x: -x['len'])
    for entry in api_log[:10]:
        print(f"\n[{entry['method']}] {entry['len']:>8} bytes  {entry['url'][45:130]}")
        # 看看里面有没有 model id
        body = entry['body']
        if 'qwen' in body.lower() or 'deepseek' in body.lower() or 'ChatGLM' in body or 'llama' in body.lower():
            print("    > 包含模型 ID！")
            try:
                d = json.loads(body)
                data = d.get('Data', {})
                if isinstance(data, dict):
                    print(f"    Data keys: {list(data.keys())[:10]}")
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 0:
                            print(f"      {k}: {len(v)} 条")
                            if isinstance(v[0], dict):
                                print(f"        keys: {list(v[0].keys())[:15]}")
                                if 'Name' in v[0] or 'ChineseName' in v[0]:
                                    print(f"        first: {v[0].get('Name', v[0].get('ChineseName', ''))[:50]}")
            except:
                pass

    # 实际滚动+翻页交互
    print("\n=== 模拟翻页查找模型API ===")
    api_log2 = []
    def on_resp2(resp):
        try:
            url = resp.url
            if '/api/' in url and resp.status == 200:
                body = resp.text()
                if body and len(body) > 1500 and ('/' in body):
                    api_log2.append({
                        'url': url,
                        'method': resp.request.method,
                        'post': resp.request.post_data if resp.request.method != 'GET' else None,
                        'len': len(body),
                        'body': body[:2000],
                    })
        except:
            pass
    page2 = context.new_page()
    page2.on("response", on_resp2)

    page2.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page2.wait_for_timeout(12000)

    # 点击"下一页"按钮附近——找分页器
    print(f"翻页前拦截到 {len(api_log2)} 个大响应")

    # 点击下一页（分页器通常 class 含 pagination）
    clicked = False
    for sel in ['.ant-pagination-next', '[class*="pagination"] [class*="next"]', '.next', 'button:has-text("下一页")']:
        try:
            el = page2.query_selector(sel)
            if el:
                el.click()
                clicked = True
                print(f"点击成功: {sel}")
                break
        except:
            pass

    if not clicked:
        # 滚动加载
        page2.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        print("改用滚动加载")

    page2.wait_for_timeout(8000)

    new_calls = [x for x in api_log2 if x not in api_log]
    print(f"翻页后新增 {len(new_calls)} 个响应:")
    for entry in sorted(new_calls, key=lambda x: -x['len'])[:5]:
        print(f"\n  {entry['method']} {entry['len']:>6}b  {entry['url'][45:120]}")
        if entry['post']:
            print(f"  post: {entry['post'][:100]}")
        # 看里面是否有 模型 id
        if '/models/' in entry['body'] or 'modelId' in entry['body'] or 'Name' in entry['body']:
            print(f"  含模型数据!")
            try:
                d = json.loads(entry['body'])
                data = d.get('Data', {})
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                            print(f"    {k}: {len(v)} items, keys: {list(v[0].keys())[:10]}")
                            if any(k in v[0] for k in ['Name', 'Downloads', 'License']):
                                print(f"    FIRST: {json.dumps(v[0], ensure_ascii=False)[:300]}")
                            break
            except:
                pass

    browser.close()