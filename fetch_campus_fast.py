import asyncio
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import async_playwright

OUT = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus.jsonl"

async def fast_fetch():
    print("开始极速拉取校招全量数据 (limit=1000 模式)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 定义一个捕捉器
        all_jobs = []
        captured_done = asyncio.Event()

        async def on_res(r):
            if "api/v1/search/job/posts" in r.url:
                try:
                    d = await r.json()
                    jobs = (d.get("data") or {}).get("job_post_list") or []
                    all_jobs.extend(jobs)
                    print(f"--- 捕获批次: {len(jobs)} 条 --- 已累计: {len(all_jobs)}")
                    if len(all_jobs) >= 7900: # 校招总量约为 7930
                        captured_done.set()
                except: pass

        page.on("response", on_res)

        # 构造超级批处理 URL (由子智能体提供)
        # portal_type=3 是校招标识, limit=1000 是核心突破
        base_url = "https://jobs.bytedance.com/campus/position?limit=1000"
        
        for offset in range(0, 8001, 1000):
            print(f"正在请求 Offset={offset}...")
            url = f"{base_url}&offset={offset}"
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(2) # 等待 API 到达

        # 最终落库
        with open(OUT, "w", encoding="utf-8") as f:
            for i, job in enumerate(all_jobs):
                record = {
                    "metadata": {"job_id": str(job.get("id")), "is_campus": True, "crawl_timestamp": datetime.now(timezone.utc).isoformat()},
                    "basic_info": {
                        "job_title": job.get("title"),
                        "category_path": [job.get("job_category", {}).get("name")],
                        "location": [c.get("name") for c in (job.get("city_list") or [])]
                    },
                    "requirements": {"raw_jd_text": (job.get("description") or "") + "\n" + (job.get("requirement") or "")}
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        print(f"校招全量落库完成！总计: {len(all_jobs)} 条")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(fast_fetch())
