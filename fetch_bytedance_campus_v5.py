import asyncio
import json
import time
from datetime import datetime, timezone
from playwright.async_api import async_playwright

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus_full_v5.jsonl"
# 从浏览器子智能体分析得出的核心项目 ID
SUBJECTS = [
    "7525009396952582407", # 2026届校园招聘
    "7194661644654577981", # 日常实习
    "7194661126919358757", # ByteIntern
]

async def full_fetch_v5():
    all_jobs = {}
    print(f"🚀 准备全量拉取字节跳动校招数据 (v5 - 分项目分桶模式)")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        page = await context.new_page()
        page.set_default_timeout(30000)
        
        async def on_res(response):
            if "/api/v1/search/job/posts" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    job_list = (data.get("data") or {}).get("job_post_list") or []
                    for job in job_list:
                        jid = str(job.get("id"))
                        if jid not in all_jobs:
                            all_jobs[jid] = {
                                "metadata": {"job_id": jid, "is_campus": True, "crawl_timestamp": datetime.now(timezone.utc).isoformat()},
                                "basic_info": {
                                    "job_title": job.get("title"),
                                    "category_path": [job.get("job_category", {}).get("name")],
                                    "location": [c.get("name") for c in (job.get("city_list") or [])]
                                },
                                "requirements": {"raw_jd_text": (job.get("description") or "") + "\n" + (job.get("requirement") or "")}
                            }
                except: pass

        page.on("response", on_res)
        
        for subject_id in SUBJECTS:
            print(f"📁 正在抓取项目 ID: {subject_id}...")
            # 每个项目内部也可能由于超过 1000 条被截断，所以我们使用多步长分页
            for offset in range(0, 4001, 100):
                try:
                    print(f"📡 {subject_id} | Offset={offset} (唯一总数: {len(all_jobs)})...")
                    url = f"https://jobs.bytedance.com/campus/position?subject={subject_id}&offset={offset}&limit=100"
                    await page.goto(url, wait_until="domcontentloaded")
                    await asyncio.sleep(1.5)
                    # 虽然我们在监听，但可以简单检测一下如果连续多次没有新 ID 增加，说明该项已到底
                except: continue

        # 保存结果
        print(f"💾 正在保存 {len(all_jobs)} 条唯一记录...")
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            for record in all_jobs.values():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
        print(f"✨ 最终抓取完毕，共捕获 {len(all_jobs)} 条唯一岗位。")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(full_fetch_v5())
