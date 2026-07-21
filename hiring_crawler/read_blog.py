"""读取 CSDN 博客文章"""
import urllib.request
import re

url = "https://blog.csdn.net/m0_73690216/article/details/151257876"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")

# 尝试提取 article_content 或 content_views
patterns = [
    r'<article[^>]*>(.*?)</article>',
    r'id="content_views"[^>]*>(.*?)</div>\s*<div class="more-toolbox"',
    r'class="article-content[^"]*"[^>]*>(.*?)</div>\s*<div class="article-tags"',
]

text = None
for pat in patterns:
    m = re.search(pat, html, re.DOTALL)
    if m:
        text = m.group(1)
        break

if not text:
    # 输出一部分HTML手动看
    print("=== RAW HTML (first 5000 chars) ===")
    print(html[:5000])
else:
    # 去除HTML标签
    clean = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL)
    clean = re.sub(r"<pre[^>]*>.*?</pre>", "\n[代码块]\n", clean, flags=re.DOTALL)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"<", "<", clean)
    clean = re.sub(r">", ">", clean)
    clean = re.sub(r"&", "&", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    print(clean[:8000])