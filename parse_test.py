import json
import re

f = open(r'D:\国际比较政治经济学\01-爬虫程序\modelscope_output\ms_users_profiles.jsonl', 'r', encoding='utf-8')
lines = f.readlines()
import random
sample = json.loads(random.choice(lines))
html = sample.get('html_snippet', '')
print(f"Owner: {sample.get('owner')}")
matches = re.findall(r'(.{0,20})(粉丝|关注|获赞|模型|数据集|Models)(.{0,20})', html)
for m in set(matches):
    print("".join(m))
