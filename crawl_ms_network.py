import os
import json
import asyncio
from playwright.async_api import async_playwright
import time
from pathlib import Path

BASE_DIR = Path(r"D:\国际比较政治经济学\01-爬虫程序")
MODELS_FILE = BASE_DIR / "modelscope_output" / "models_all.json"
OUTPUT_FILE = BASE_DIR / "modelscope_output" / "ms_users_profiles.jsonl"
STATE_FILE = BASE_DIR / "modelscope_output" / "state_ms_users.json"

async def scrape_user_profile(page, owner):
    """抓取用户/组织的粉丝数、关注数和获赞数"""
    url = f"https://www.modelscope.cn/profile/{owner}" # 可能也会重定向到 organization
    
    result = {"owner": owner, "status": "success", "crawled_at": time.time()}
    try:
        response = await page.goto(url, wait_until="networkidle", timeout=20000)
        # 若是 404，可能是组织主页
        if response.status == 404:
            url = f"https://www.modelscope.cn/organization/{owner}"
            await page.goto(url, wait_until="networkidle", timeout=20000)
        
        await asyncio.sleep(2)
        
        # 提取统计数据 (粉丝数，关注数等) - 这里依赖页面 DOM 结构，需要实际运行时抓取文本
        # 由于我们无法提前准确知道 DOM Selector，我们将提取整个 body 的文本内容进行后处理
        page_content = await page.content()
        result["html_snippet"] = page_content[:15000] # 保存部分 HTML 用于分析结构
        
        # 尝试拦截任何含有 user/org profile 的 API
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result

async def main():
    if not MODELS_FILE.exists():
        return

    with open(MODELS_FILE, "r", encoding="utf-8") as f:
        models = json.load(f)
    
    # 提取所有唯一的 Owner
    owners = list(set(m.get("Owner") for m in models if m.get("Owner")))
    
    completed = set()
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            completed = set(json.load(f))
            
    print(f"Total Unique Owners: {len(owners)}, Completed: {len(completed)}, Remaining: {len(owners) - len(completed)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
            for i, owner in enumerate(owners):
                if owner in completed:
                    continue

                print(f"[{i+1}/{len(owners)}] Scraping profile for: {owner} ...")
                result = await scrape_user_profile(page, owner)
                
                out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_f.flush()
                
                completed.add(owner)
                with open(STATE_FILE, "w") as sf:
                    json.dump(list(completed), sf)
                
                await asyncio.sleep(1)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
