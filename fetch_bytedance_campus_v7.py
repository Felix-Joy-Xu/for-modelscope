import asyncio
import json
import time
from datetime import datetime, timezone
from playwright.async_api import async_playwright

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus_full_v7.jsonl"
# 招聘项目 ID
SUBJECTS = [
    "7525009396952582407", # 2026届校园招聘
    "7194661644654577981", # 日常实习
    "7194661126919358757", # ByteIntern
]
# 职位类别 ID (从浏览器子智能体实时提取)
CATEGORY_MAP = {
    "研发": "6704215862603155720",
    "运营": "6704215882479962371",
    "产品": "6704215864629004552",
    "职能 / 支持": "6704215913488451847",
    "设计": "6709824272514156812",
    "销售": "6704215923982592263",
    "市场": "6704215888914024707",
    "教研教学": "6704215951551736077",
    "游戏策划": "6850051244434655495"
}

async def full_fetch_v7():
    all_jobs = {}
    print(f"🚀 准备深度拉取字节跳动校招全量数据 (v7 - 项目+类别 ID 分桶)")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        page = await context.new_page()
        page.set_default_timeout(60000)
        
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
        
        for sub_id in SUBJECTS:
            for cat_name, cat_id in CATEGORY_MAP.items():
                print(f"📁 正在抓取项目:[{sub_id}] 类别:[{cat_name}]...")
                # 遍历分页以确保在这个 (项目+类别) 桶内拿到所有数据
                # 由于分桶细，每个通常不会超过 1000 条，所以翻 10 页足够
                for offset in range(0, 1001, 100):
                    try:
                        print(f"📡 桶进度: {cat_name} | Offset={offset} | 累计唯一 ID: {len(all_jobs)}...")
                        url = f"https://jobs.bytedance.com/campus/position?subject={sub_id}&category={cat_id}&offset={offset}&limit=100"
                        await page.goto(url, wait_until="domcontentloaded")
                        await asyncio.sleep(1.5)
                    except: continue

        # 保存结果
        print(f"💾 正在保存 {len(all_jobs)} 条唯一记录...")
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            for record in all_jobs.values():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
        print(f"✨ 抓取任务圆满完成! 最终捕获量: {len(all_jobs)} 条唯一记录。")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(full_fetch_v7())
