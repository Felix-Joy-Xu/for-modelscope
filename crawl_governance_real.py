"""抓取魔搭真正的制度文本URL"""
import os, urllib.parse
from datetime import datetime
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 从首页发现的真实URL + 新发现的底部链接
TARGETS = [
    ("about", "/protocol/关于我们", "关于我们"),
    ("user_agreement", "/protocol/用户协议", "用户协议"),
    ("privacy_policy", "/protocol/隐私政策", "隐私政策"),
    ("open_source_code_of_conduct", "/protocol/开源行为准则", "开源行为准则"),
    ("ai_ethics", "/protocol/人工智能伦理倡议书", "人工智能伦理倡议书"),
    ("contact_us", "/protocol/联系我们", "联系我们"),
]

BASE = "https://www.modelscope.cn"

CONTENT_SELECTORS = [
    "article",
    "[class*='protocol']",
    "[class*='agreement']",
    "[class*='content']",
    "[class*='markdown']",
    "[class*='rich-text']",
    "[class*='document']",
    "[class*='page']",
    "main",
    "#root",
    "body",
]

def extract_text(page):
    """提取页面中最长的文本内容"""
    # 方法1: 优先用Playwright的JS提取
    text = page.evaluate("""() => {
        // 优先找内容容器
        let selectors = [
            'article', '[class*="protocol"]', '[class*="content"]',
            '[class*="markdown"]', '[class*="rich-text"]', '[class*="document"]',
            'main', '#root'
        ];
        let best = '';
        for (let sel of selectors) {
            let el = document.querySelector(sel);
            if (el) {
                let t = el.innerText || el.textContent || '';
                // 过滤导航/页脚
                let lines = t.split('\\n').filter(l => l.trim().length > 1);
                let cleaned = lines.join('\\n').trim();
                if (cleaned.length > best.length) best = cleaned;
            }
        }
        return best || document.body?.innerText || '';
    }""")
    return text

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 900})
    page = context.new_page()

    results = []

    for name, path, label in TARGETS:
        url = BASE + path
        print(f"\n--- {label} ---")
        print(f"  URL: {url}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)
            # 试试再多等一会
            if not page.evaluate("() => document.body?.innerText?.length || 0 > 200"):
                page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  ERR: {e}")
            continue

        text = extract_text(page)
        print(f"  Text: {len(text)} chars")

        if len(text) < 50:
            print(f"  内容过短，跳过")
            continue

        # 保存
        filepath = os.path.join(OUTPUT_DIR, f"governance_{name}.txt")
        header = f"""# {label}
# 源URL: {url}
# 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# 文本长度: {len(text)} chars
{'=' * 80}

"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + text)

        results.append((name, label, filepath))
        # 预览
        for line in text.split("\n")[:5]:
            if line.strip():
                print(f"  | {line[:70]}")
        print(f"  -> {os.path.basename(filepath)}")

    browser.close()

# 汇总
print(f"\n{'='*60}")
print(f"完成: {len(results)}/{len(TARGETS)}")
print(f"{'='*60}")
for name, label, path in results:
    size = os.path.getsize(path)
    print(f"  {label:12s} {size:>8,} bytes  governance_{name}.txt")