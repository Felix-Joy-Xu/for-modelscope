import re

html = open(r"D:\hiring_data\boss_debug.html", "r", encoding="utf-8").read()

# 找所有 class 中包含 job/card/list 的
classes = set(re.findall(r'class=[\"\']([^\"\']+)[\"\']', html))
job_related = [c for c in classes if "job" in c.lower() or "card" in c.lower() or "list" in c.lower()]
for c in sorted(job_related):
    print(c)

print("\n--- all li classes ---")
li_classes = set(re.findall(r'<li[^>]*class=[\"\']([^\"\']+)[\"\']', html))
for c in sorted(li_classes):
    print(c)

print("\n--- looking for job-card-like structures in the body ---")
# 搜包含 job-card 的片段
for m in re.finditer(r'<[^>]*job-card[^>]*>[^<]{0,200}', html):
    print(m.group()[:200])

print("\n--- search-result ---")
for m in re.finditer(r'<[^>]*search[^>]*result[^>]*>', html):
    print(m.group())

print("\n--- all unique top-level tags inside #app or body ---")
# 找所有id
ids = set(re.findall(r'id=[\"\']([^\"\']+)[\"\']', html))
for i in sorted(ids):
    print(i)