import asyncio
import json
import random
import time
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# --- 配置区 ---
OUTPUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus.jsonl"
STATE_FILE = r"c:\Users\22735\Desktop\ai\data\state\state_campus.json"
RAW_DIR = Path(r"c:\Users\22735\Desktop\ai\data\raw\bytedance_campus")

def ensure_parent_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

def load_state(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"count": 0, "seen_job_ids": []}

def save_state(path: Path, state):
    ensure_parent_dir(path)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def append_jsonl(path: str, record: dict):
    p = Path(path)
    ensure_parent_dir(p)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def make_record(platform, job_id, job_title, category_path, location, publish_date, raw_jd_text):
    return {
        "metadata": {
            "platform": platform,
            "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "is_campus": True
        },
        "basic_info": {
            "job_title": job_title,
            "category_path": category_path,
            "location": location,
            "publish_date": publish_date,
        },
        "requirements": {
            "raw_jd_text": raw_jd_text
        }
    }

async def crawl_campus(limit=None):
    state = load_state(Path(STATE_FILE))
    seen_job_ids = set(state.get("seen_job_ids", []))
    count = state.get("count", 0)
    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        await stealth_async(page)

        async def on_response(resp):
            if "/api/v1/search/job/posts" in resp.url:
                try:
                    payload = await resp.json()
                    captured.append(payload)
                except:
                    pass

        page.on("response", on_response)
        
        all_categories = ["研发", "运营", "产品", "职能 / 支持", "设计", "市场", "销售", "游戏策划", "教研教学"]
        
        for cat_name in all_categories:
            print(f"\n--- 开始抓取校招分类: {cat_name} ---")
            await page.goto("https://jobs.bytedance.com/campus/position", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
            try:
                # 尝试选择分类
                cat_btn = page.get_by_text(cat_name, exact=True).first
                if await cat_btn.is_visible():
                    await cat_btn.click()
                    await page.wait_for_timeout(2000)
                else:
                    # 备选：尝试下拉展开
                    filter_box = page.get_by_placeholder("职类").first
                    if await filter_box.is_visible():
                        await filter_box.click()
                        await page.wait_for_timeout(1000)
                        await page.get_by_text(cat_name, exact=True).last.click()
                        await page.wait_for_timeout(2000)
            except:
                print(f"未能选择分类 {cat_name}，尝试全局搜索...")

            curr_p = 1
            while curr_p <= 1000:
                print(f"[{cat_name}] 第 {curr_p} 页 | 已捕获总量: {count}")
                pre_len = len(captured)
                
                try:
                    next_btn = page.locator("li.atsx-pagination-next:not(.atsx-pagination-disabled)").first
                    if not await next_btn.is_visible():
                        await page.keyboard.press("End")
                        await page.wait_for_timeout(1000)
                    
                    if await next_btn.is_visible():
                        await next_btn.click()
                        curr_p += 1
                        # 等待响应
                        t0 = time.time()
                        while len(captured) == pre_len and time.time() - t0 < 8:
                            await asyncio.sleep(0.5)
                    else:
                        break
                except:
                    break

                # 实时保存
                if len(captured) > pre_len:
                    for item in captured[pre_len:]:
                        jobs = (item.get("data") or {}).get("job_post_list") or []
                        for j in jobs:
                            jid = str(j.get("id"))
                            if jid in seen_job_ids: continue
                            seen_job_ids.add(jid)
                            title = j.get("title")
                            locs = [c.get("name") for c in (j.get("city_list") or [])]
                            raw_jd = (j.get("description") or "") + "\n" + (j.get("requirement") or "")
                            
                            append_jsonl(OUTPUT_FILE, make_record(
                                "bytedance", jid, title, [cat_name], locs, None, raw_jd
                            ))
                            count += 1
                    
                    state["count"] = count
                    state["seen_job_ids"] = list(seen_job_ids)
                    save_state(Path(STATE_FILE), state)

                if limit and count >= limit: break
                await asyncio.sleep(random.uniform(1, 3))
            
            if limit and count >= limit: break

        await browser.close()
    return count

if __name__ == "__main__":
    asyncio.run(crawl_campus(limit=100000))
