"""用 Playwright 抓取魔搭模型库页面渲染后的模型列表"""
import os, json, time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    # 拦截 API 调用看请求
    api_results = []
    def on_response(resp):
        url = resp.url
        if '/api/' in url and ('model' in url.lower() or 'list' in url.lower() or 'page' in url.lower()):
            try:
                body = resp.text()
                if body and len(body) > 10:
                    api_results.append({'url': url, 'status': resp.status, 'body_preview': body[:300]})
            except:
                pass
    page.on("response", on_response)

    print("=== 打开模型库页面 ===")
    page.goto("https://www.modelscope.cn/models", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(10000)  # 等渲染

    # 滚动触发加载
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(3000)

    # 拦截到的API
    print(f"\n拦截到 {len(api_results)} 个 API 调用:")
    for r in api_results[:10]:
        print(f"  [{r['status']}] {r['url'][:100]}")
        print(f"    body: {r['body_preview'][:150]}")

    # 从DOM提取模型卡片
    print("\n=== 从DOM提取模型卡片 ===")
    cards = page.evaluate("""() => {
        let results = [];
        // 找所有链接到 /models/ 的卡片
        let links = document.querySelectorAll('a[href*="/models/"]');
        let seen = new Set();
        for (let a of links) {
            let href = a.getAttribute('href') || '';
            // 模型链接格式: /models/{org}/{model}
            let match = href.match(/\\/models\\/([^/]+\\/[^/?#]+)/);
            if (match) {
                let modelId = match[1];
                if (seen.has(modelId)) continue;
                seen.add(modelId);
                // 找父容器提取更多信息
                let card = a.closest('[class*="card"]') || a.closest('[class*="item"]') || a.parentElement;
                let text = card ? card.innerText : a.innerText;
                results.push({
                    modelId: modelId,
                    href: href,
                    text: text.substring(0, 500),
                });
            }
        }
        return results;
    }""")
    print(f"找到 {len(cards)} 个模型卡片")
    for c in cards[:5]:
        model_id = c.get('modelId', '').encode('ascii', 'replace').decode('ascii')
        text_preview = c.get('text', '').encode('ascii', 'replace').decode('ascii')[:200]
        print(f"  {model_id}: {text_preview}")

    # 保存
    with open(os.path.join(OUTPUT_DIR, 'probe_models_dom.json'), 'w', encoding='utf-8') as f:
        json.dump({'api_calls': api_results[:20], 'dom_cards': cards[:50]}, f, ensure_ascii=False, indent=2)
    print(f"\n保存到 probe_models_dom.json")

    browser.close()