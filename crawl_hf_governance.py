#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补充 HF 治理文本（从 hf-mirror.com 抓四份）"""
import os, requests, time
from bs4 import BeautifulSoup

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
HF_DIR = os.path.join(OUTPUT_DIR, "hf_governance")
os.makedirs(HF_DIR, exist_ok=True)

# hf-mirror 是 hf-mirror.com，pages 和 docs 在对应路径
HF_TARGETS = [
    ("terms_of_service", "https://hf-mirror.com/terms", "Terms of Service"),
    ("privacy_policy", "https://hf-mirror.com/privacy", "Privacy Policy"),
    ("acceptable_use", "https://hf-mirror.com/content-policy", "Acceptable Use Policy"),
    ("community_guidelines", "https://hf-mirror.com/community-guidelines", "Community Guidelines"),
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml",
})

for name, url, label in HF_TARGETS:
    print(f"\n--- {label} ---")
    try:
        r = session.get(url, timeout=30)
        print(f"  status: {r.status_code}, bytes: {len(r.text)}")
        if r.status_code != 200 or len(r.text) < 500:
            continue

        # 优先提取正文
        try:
            soup = BeautifulSoup(r.text, "lxml")
            # 去掉头尾的 nav/footer
            for tag in soup.select("script, style, nav, footer, header, aside"):
                tag.decompose()
            main = (soup.find("main") or soup.select_one("[class*='content']") 
                    or soup.find("body"))
            text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
            # 清理空行
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            text = "\n".join(lines)
        except:
            text = r.text

        path = os.path.join(HF_DIR, f"hf_{name}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {label}\n# Source: {url}\n# Length: {len(text)} chars\n{'='*80}\n\n{text}")
        print(f"  Saved: hf_{name}.txt ({len(text)} chars)")
        # 预览
        for line in lines[:3]:
            print(f"    | {line[:80]}")
    except Exception as e:
        print(f"  ERR: {str(e)[:80]}")
    time.sleep(0.5)

# 汇总
print(f"\n{'='*60}")
print(f"HF 治理文本完成")
print(f"{'='*60}")
for fn in sorted(os.listdir(HF_DIR)):
    p = os.path.join(HF_DIR, fn)
    sz = os.path.getsize(p)
    print(f"  {fn:40s} {sz:>6,} bytes")