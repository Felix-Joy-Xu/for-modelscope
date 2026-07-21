"""快速测试：用和爬虫完全一样的方式打开浏览器，访问3个缺失职位，看看实际情况"""
import json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from DrissionPage import ChromiumPage, ChromiumOptions

# 加载待抓取列表
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

# 从数据库也加载
import sqlite3
conn = sqlite3.connect(r"D:\hiring_data\boss_api\boss_jobs.db")
cur = conn.cursor()
cur.execute("SELECT encryptJobId FROM jobs WHERE jd_text IS NOT NULL AND jd_text != ''")
for row in cur.fetchall():
    scraped.add(row[0])
conn.close()

# 找5个还没抓到的
targets = []
with open(r"D:\hiring_data\boss_api\missing_jd_jobs.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            jid = json.loads(line)["encryptJobId"]
            if jid not in scraped:
                targets.append(jid)
                if len(targets) >= 5:
                    break

print(f"将测试 {len(targets)} 个职位ID")

co = ChromiumOptions()
co.set_argument("--no-first-run")
co.set_argument("--no-default-browser-check")
co.set_argument("--disable-blink-features=AutomationControlled")
co.auto_port()

page = ChromiumPage(co)
print(f"浏览器已启动, URL: {page.url}")

# 先访问 BOSS 直聘首页
page.get("https://www.zhipin.com/web/geek/job?city=101010100")
time.sleep(3)
print(f"首页标题: {page.title}")
print(f"首页URL: {page.url}")

for i, jid in enumerate(targets):
    url = f"https://www.zhipin.com/job_detail/{jid}.html"
    print(f"\n--- 测试 {i+1}/{len(targets)}: {jid} ---")
    print(f"URL: {url}")
    
    try:
        page.get(url)
    except Exception as e:
        print(f"导航失败: {e}")
        continue
    
    time.sleep(3)
    
    try:
        print(f"  标题: {page.title}")
        print(f"  实际URL: {page.url}")
    except Exception as e:
        print(f"  获取标题失败: {e}")
    
    try:
        body = page.run_js("return document.body ? document.body.innerText.substring(0, 300) : 'NO BODY'")
        print(f"  Body预览: {body[:200]}")
    except Exception as e:
        print(f"  获取body失败: {e}")
    
    # 尝试提取 JD
    try:
        jd = page.run_js("""
            var el = document.querySelector('.job-sec-text');
            if (!el) return 'NO .job-sec-text';
            return el.innerText.substring(0, 100);
        """)
        print(f"  JD提取结果: {jd}")
    except Exception as e:
        print(f"  JD提取失败: {e}")

page.quit()
print("\n测试完毕!")
