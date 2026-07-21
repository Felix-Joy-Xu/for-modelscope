import asyncio
import json
import time
from datetime import datetime, timezone
from playwright.async_api import async_playwright

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus_full_v3.jsonl"
TOTAL_TO_FETCH = 7943  # 目标总量

async def full_fetch_campus():
    all_jobs = {}
    print(f"🚀 准备深度拉取字节跳动校园招聘数据 (预期总量: {TOTAL_TO_FETCH})")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        page = await context.new_page()
        
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
                except Exception:
                    pass

        page.on("response", on_res)
        
        # 尝试通过循环 offset 触发 API
        # 字节跳动界面默认可能不显示 limit=1000 的 UI，但 API 接受
        # 我们直接请求循环的分页 URL
        for offset in range(0, 8001, 100):
            print(f"📡 正在触发查询: Offset={offset} / 已捕获唯一岗位: {len(all_jobs)}...")
            # 拼接 URL 以触发前端发起 API 请求
            url = f"https://jobs.bytedance.com/campus/position?offset={offset}&limit=100"
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(1) # 给 API 响应预留时间
            
            # 如果已经拿全了或者不再增长，可以提前退
            if len(all_jobs) >= TOTAL_TO_FETCH:
                print(f"✅ 捕获量已达到目标: {len(all_jobs)}")
                break

        # 保存结果
        print(f"💾 正在保存 {len(all_jobs)} 条唯一记录...")
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            for record in all_jobs.values():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
        print(f"✨ 抓取完成！保存至: {OUT_FILE}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(full_fetch_campus())
