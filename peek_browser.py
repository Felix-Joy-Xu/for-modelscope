from DrissionPage import ChromiumPage
import sys
sys.stdout.reconfigure(encoding='utf-8')

try:
    page = ChromiumPage()
    url = page.url
    title = page.title
    body_text = page.run_js("return document.body ? document.body.innerText.substring(0, 500) : 'NO BODY'")
    html = page.html[:500]
    
    print(f"当前 URL: {url}")
    print(f"页面标题: {title}")
    print(f"Body 内容前 500 字: \n{body_text}\n")
    print(f"HTML 源码前 500 字: \n{html}\n")
except Exception as e:
    print(f"无法连接到浏览器: {e}")
