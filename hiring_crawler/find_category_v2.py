"""V2: 抓取 Boss 直聘搜索页筛选区域的标签文本"""
from DrissionPage import ChromiumPage
import time

page = ChromiumPage()
page.get("https://www.zhipin.com/web/geek/job?city=100010000")
time.sleep(8)

# 先取整个 body 文本看看有哪些可见文字
body = page.ele("body", timeout=5)
full_text = body.text if body else ""
print(f"Total text length: {len(full_text)}")

# 找出前1000字符，看有哪些筛选标签
lines = [l.strip() for l in full_text.split("\n") if l.strip()]
print("\n=== First 80 non-empty lines ===")
for i, line in enumerate(lines[:80]):
    print(f"  {i:3d}: {line[:100]}")

# 找可能的分类型关键词
print("\n=== Looking for category keywords ===")
for kw in ["不限", "技术", "后端", "前端", "产品", "设计", "运营", "市场", "销售", "人事", "财务", "法务", "金融", "医疗", "教育", "后端开发", "前端开发", "Java", "Python", "测试", "运维", "算法", "数据"]:
    count = full_text.count(kw)
    if count > 0:
        # 找前后文
        idx = full_text.find(kw)
        ctx = full_text[max(0, idx-20):idx+len(kw)+20]
        print(f"  '{kw}': {count} occurrences, context: ...{ctx}...")

# 也看看 HTML 中关于 condition 的区域
print("\n=== HTML condition 区域 ===")
body_html = page.ele("body", timeout=3).html if body else page.html
# 找包含 职位 或 分类 的 span/div
import re
for m in re.finditer(r'<(span|div|a|li|label)[^>]*>([^<]*[职位分类类型][^<]*)</\1>', body_html):
    print(f"  {m.group(0)[:200]}")