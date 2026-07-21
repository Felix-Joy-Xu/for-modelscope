"""分析 Boss 直聘职位类型分类选择器"""
from DrissionPage import ChromiumPage
import time

page = ChromiumPage()
page.get("https://www.zhipin.com/web/geek/job?city=100010000")
time.sleep(6)

print("=== 页面上的职位类型筛选区域 ===")

# 方法1: 找 condition-bar 区域
for sel in [".condition-bar", ".search-condition", ".job-conditions", ".condition-box", ".condition-row"]:
    els = page.eles(sel, timeout=2)
    if els:
        print(f"\n{sel}: {len(els)}")
        for e in els:
            print(f"  text: {e.text[:150]}")
            print(f"  html: {e.html[:300]}")

# 方法2: 直接找所有包含 classify/type 的URL pattern
print("\n=== URL 参数分析 ===")
page.get("https://www.zhipin.com/web/geek/job?city=100010000")
time.sleep(4)

# 点击"职位类型"触发下拉
job_type_elements = page.eles("text:职位类型", timeout=2)
if not job_type_elements:
    job_type_elements = page.eles("text:职位类别", timeout=1)

print(f"职位类型元素: {len(job_type_elements)}")
for el in job_type_elements:
    print(f"  tag={el.tag}, class={el.attr('class')}, text={el.text}")
    # 尝试点击触发
    try:
        el.click()
        time.sleep(2)
        print("  -> 已点击")
    except Exception as ex:
        print(f"  -> 点击失败: {ex}")

# 方法3: 直接测试 URL 参数
import requests
print("\n=== 测试不同 position 参数 ===")
# Boss 直聘的职位分类参数通常是 position=
base = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
test_params = [
    {"query": "后端", "city": "100010000", "experience": "", "degree": "", "page": "1"},
    {"query": "", "city": "100010000", "position": "100101", "page": "1"},  # Java
    {"query": "", "city": "100010000", "position": "100102", "page": "1"},  # C
]

# 方法4: 查看页面所有 a 标签的 href，找包含 position 的
print("\n=== 所有包含 position 的链接 ===")
links = page.eles("tag:a", timeout=2)
for a in links:
    href = a.attr("href") or ""
    if "position" in href:
        print(f"  {a.text[:50]} -> {href}")
        if len([1 for aa in links if "position" in (aa.attr("href") or "")]) > 20:
            break

# 方法5: 直接看页面渲染后的HTML中关于分类的部分
body = page.ele("body", timeout=3)
html_snippet = body.html if body else page.html
# 找所有包含 "后端" "前端" 但不含 job-detail 的链接区域
import re
pos_links = re.findall(r'<a[^>]*href="[^"]*position[^"]*"[^>]*>([^<]+)</a>', html_snippet)
print(f"\n=== HTML中 position 链接文本 ({len(pos_links)}): ===")
for t in set(pos_links[:30]):
    print(f"  {t}")