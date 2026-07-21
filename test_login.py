"""验证登录状态并测试抓取"""
import json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from DrissionPage import ChromiumPage

# 连接已有浏览器（不用 auto_port，直接接管用户打开的浏览器）
page = ChromiumPage()
print(f"当前URL: {page.url}")
print(f"当前标题: {page.title}")

# 测试访问一个职位
scraped = set()
with open(r"D:\hiring_data\boss_api\boss_jd_full.jsonl", "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        if line.strip():
            try:
                d = json.loads(line)
                if d.get("jd_text") and len(d.get("jd_text")) > 50:
                    scraped.add(d["encryptJobId"])
            except:
                pass

import sqlite3
conn = sqlite3.connect(r"D:\hiring_data\boss_api\boss_jobs.db")
cur = conn.cursor()
cur.execute("SELECT encryptJobId FROM jobs WHERE jd_text IS NOT NULL AND jd_text != ''")
for row in cur.fetchall():
    scraped.add(row[0])
conn.close()

targets = []
with open(r"D:\hiring_data\boss_api\missing_jd_jobs.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            jid = json.loads(line)["encryptJobId"]
            if jid not in scraped:
                targets.append(jid)
                if len(targets) >= 3:
                    break

for i, jid in enumerate(targets):
    url = f"https://www.zhipin.com/job_detail/{jid}.html"
    print(f"\n--- 测试 {i+1}: {jid} ---")
    try:
        page.get(url)
        time.sleep(3)
        print(f"  标题: {page.title}")
        print(f"  URL: {page.url}")
        
        jd = page.run_js("""
            var el = document.querySelector('.job-sec-text');
            if (!el) return 'NO .job-sec-text';
            return el.innerText.substring(0, 150);
        """)
        print(f"  JD: {jd}")
    except Exception as e:
        print(f"  错误: {e}")

print("\n验证完毕!")
