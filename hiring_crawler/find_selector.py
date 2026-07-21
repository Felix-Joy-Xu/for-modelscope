"""分析 Boss 直聘职位列表的真实 DOM 结构"""
from DrissionPage import ChromiumPage
import time

page = ChromiumPage()
page.get("https://www.zhipin.com/web/geek/job?query=字节跳动&city=100010000")
time.sleep(8)

# 用 text: 找到职位链接
job_anchors = page.eles("text:工程师", timeout=5)
print(f"Found {len(job_anchors)} elements with '工程师'")
for i, a in enumerate(job_anchors[:5]):
    print(f"\n--- Anchor #{i} ---")
    print(f"  tag: {a.tag}")
    print(f"  text: {a.text[:80]}")
    print(f"  attrs: {a.attrs}")
    # 找父级树
    parent = a
    for depth in range(10):
        parent = parent.parent()
        if not parent:
            break
        cls = parent.attr("class") or ""
        tag = parent.tag
        first_text = (parent.text or "")[:60].replace("\n", " ")
        print(f"  parent L{depth+1}: <{tag} class='{cls[:80]}'> {first_text}")

# 找搜索结果的容器
print("\n\n=== Looking for result container ===")
for sel in [
    ".search-job-result",
    ".job-result",
    ".job-list",
    ".search-job-list",
    '[class*="search"]',
    '[class*="result"]',
    '[class*="job-list"]',
]:
    try:
        els = page.eles(sel, timeout=2)
        if els:
            print(f"{sel}: {len(els)} found")
    except:
        pass

# 直接看 body 下可能的主结构
print("\n=== Main content structure ===")
body = page.ele("body", timeout=3)
if body:
    # body 直接子元素
    for child in body.children(timeout=1)[:30]:
        tag = child.tag
        cls = (child.attr("class") or "")[:80]
        tid = (child.attr("id") or "")[:40]
        text_preview = (child.text or "")[:60].replace("\n", " ")
        if text_preview.strip():
            print(f"  <{tag} id='{tid}' class='{cls}'> {text_preview}")

# 直接通过 XPath 找包含职位名的父容器
print("\n=== Parent of job links (XPath) ===")
for a in job_anchors[:3]:
    try:
        # 向上找最近的 li 或 div 容器
        ancestor = a
        while ancestor:
            ancestor = ancestor.parent()
            if not ancestor:
                break
            tag = ancestor.tag
            cls = (ancestor.attr("class") or "")
            if tag in ("li", "div") and "job" in cls.lower():
                print(f"\n  Job container: <{tag} class='{cls}'>")
                # 找这个容器下的薪资
                sal = ancestor.ele("[class*='salary']", timeout=0.5)
                if sal:
                    print(f"    salary: {sal.text}")
                break
    except:
        pass