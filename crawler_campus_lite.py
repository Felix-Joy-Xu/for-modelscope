import asyncio
import json
import random
import time
import os
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# --- Data Paths ---
OUT = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus.jsonl"
STATE = r"c:\Users\22735\Desktop\ai\data\state\state_campus.json"

def save(j):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(j, ensure_ascii=False) + "\n")

async def run_crawl():
    if os.path.exists(STATE):
        with open(STATE, "r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        state = {"seen": [], "total": 0}
    
    seen = set(state["seen"])
    count = state["total"]

    print(f"Starting Campus Crawl... Existing: {count}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        await stealth_async(page)

        captured = []
        async def on_res(r):
            if "search/job/posts" in r.url:
                try:
                    d = await r.json()
                    captured.append(d)
                except: pass
        page.on("response", on_res)

        cats = ["研发", "运营", "产品", "职能 / 支持", "设计", "市场", "销售", "游戏策划"]
        for cat in cats:
            print(f"Category: {cat}")
            await page.goto("https://jobs.bytedance.com/campus/position", wait_until="networkidle")
            try:
                await page.get_by_text(cat, exact=True).first.click()
                await page.wait_for_timeout(2000)
            except: pass

            for p_idx in range(1, 1001):
                raw_len = len(captured)
                print(f"[{cat}] Page {p_idx} | Total {count}")
                
                next_btn = page.locator(".atsx-pagination-next:not(.atsx-pagination-disabled)").first
                if not await next_btn.is_visible():
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(1000)
                
                if await next_btn.is_visible():
                    await next_btn.click()
                    # wait for new response
                    t = time.time()
                    while len(captured) == raw_len and time.time() - t < 10:
                        await asyncio.sleep(0.5)
                else: break

                # process
                if len(captured) > raw_len:
                    for pack in captured[raw_len:]:
                        items = (pack.get("data") or {}).get("job_post_list") or []
                        for i in items:
                            jid = str(i.get("id"))
                            if jid in seen: continue
                            seen.add(jid)
                            record = {
                                "id": jid, "title": i.get("title"), "cat": [cat],
                                "loc": [c.get("name") for c in (i.get("city_list") or [])],
                                "jd": (i.get("description") or "") + "\n" + (i.get("requirement") or "")
                            }
                            save({"metadata":{"job_id":jid, "is_campus":True}, "basic_info":record})
                            count += 1
                    
                    with open(STATE, "w", encoding="utf-8") as f:
                        json.dump({"seen": list(seen), "total": count}, f)
                
                await asyncio.sleep(random.uniform(1.5, 3.5))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crawl())
