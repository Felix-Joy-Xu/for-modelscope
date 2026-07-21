import asyncio
import json
import time
from datetime import datetime, timezone
from playwright.async_api import async_playwright

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus_full_v4.jsonl"
TOTAL_TO_FETCH = 7943 

async def full_fetch_campus():
    all_jobs = {}
    print(f"🚀 准备全量拉取字节跳动校招数据 (v4 - 分类+多页模式)")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 模拟真实浏览器，增加连接耐心
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        page = await context.new_page()
        page.set_default_timeout(60000) # 60秒超时
        
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
        
        # 1. 首先尝试全局大步长抓取 (Offset 0-1000)
        # 很多时候 limit=1000 是单次最大上限
        for offset in [0, 1000]:
            try:
                print(f"📡 抓取全局 Offset={offset} (Limit=1000)...")
                await page.goto(f"https://jobs.bytedance.com/campus/position?offset={offset}&limit=1000", wait_until="load")
                await asyncio.sleep(3)
            except: pass

        # 2. 如果依然没到目标总量，遍历主要分类以规避 1000 条窗口限制
        # 分类 ID 列表 (研发: 6710609062334810375, 运营: 6710609062334810376 等)
        # 我们直接让页面加载所有分类的聚合视图，只要触发了 API 请求录入即可
        # 简单的办法是多刷几页不同的分类
        print(f"🔄 当前累计: {len(all_jobs)} 条。正在尝试分类渗透...")
        
        # 我们直接强制遍历 100 个页码 (Offset 0-8000, 步长 100)
        # 即使 Timeout 也会忽略并继续，确保尽量多的触发 API 拦截
        for offset in range(0, 8001, 100):
            if len(all_jobs) >= TOTAL_TO_FETCH: break
            try:
                print(f"📡 触发 Offset={offset} (已获 {len(all_jobs)})...")
                # 随机增加一个参数打破缓存
                await page.goto(f"https://jobs.bytedance.com/campus/position?offset={offset}&limit=100&_t={int(time.time()*1000)}", wait_until="domcontentloaded")
                await asyncio.sleep(1)
            except: continue

        # 保存结果
        print(f"💾 正在保存 {len(all_jobs)} 条唯一记录...")
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            for record in all_jobs.values():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
        print(f"✨ 最终抓取量: {len(all_jobs)}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(full_fetch_campus())
