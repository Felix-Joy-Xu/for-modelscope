import asyncio
import json
import time
from datetime import datetime, timezone
from playwright.async_api import async_playwright

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus_full_v6.jsonl"
SUBJECTS = ["7525009396952582407", "7194661644654577981", "7194661126919358757"]
# 使用行业大类作为分桶键，确保每个桶的返回量不会撞到 1000 条上限
CATEGORIES = ["研发", "运营", "产品", "设计", "市场", "销售", "职能 / 支持", "其他"]

async def full_fetch_v6():
    all_jobs = {}
    print(f"🚀 准备全量拉取字节跳动校招数据 (v6 - 极细粒度分桶)")
    
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
        
        # 开始三重循环抓取: 招聘批次 * 职务大类 * 分页
        for sub_id in SUBJECTS:
            for cat in CATEGORIES:
                print(f"📁 项目: {sub_id} | 类别: {cat}...")
                for offset in range(0, 1501, 100): # 每个桶内的分页
                    try:
                        print(f"📡 {sub_id}-{cat} | Offset={offset} (累计: {len(all_jobs)})...")
                        # 将 URL 进行编码发送给页面
                        # 注意: URL 参数中如果有特殊符号或中文，Playwright 会透明处理
                        url = f"https://jobs.bytedance.com/campus/position?subject={sub_id}&job_category={cat}&offset={offset}&limit=100"
                        await page.goto(url, wait_until="domcontentloaded")
                        await asyncio.sleep(1.2)
                        
                        # 简单的终止逻辑：如果我们在这个类别里分页了但没有新 ID 进入，说明已经拿完了这一类
                        # 这里为了保险，还是走完计划的循环步长
                    except: continue

        # 保存结果
        print(f"💾 正在保存 {len(all_jobs)} 条唯一记录...")
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            for record in all_jobs.values():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
        print(f"✨ 抓取完毕! 最终捕获量: {len(all_jobs)}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(full_fetch_v6())
