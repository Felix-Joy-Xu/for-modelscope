import asyncio
from playwright.async_api import async_playwright
import json
import time
from pathlib import Path

BASE_DIR = Path(r"D:\国际比较政治经济学\01-爬虫程序")
OUTPUT_FILE = BASE_DIR / "modelscope_output" / "ms_leaderboards.jsonl"

async def scrape_leaderboard(page, url, name):
    result = {"name": name, "url": url, "crawled_at": time.time(), "status": "success"}
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(5)
        
        # 尝试拦截表格数据请求
        page_content = await page.content()
        result["html_snippet"] = page_content[:20000] # 保存以供离线解析
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result

async def main():
    leaderboards = [
        {"name": "LLM_Evaluation", "url": "https://www.modelscope.cn/leaderboard/58/ranking?type=free"},
        {"name": "AIGC_Evaluation", "url": "https://www.modelscope.cn/leaderboard/59/ranking?type=free"}
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
            for board in leaderboards:
                print(f"Scraping leaderboard: {board['name']} ...")
                res = await scrape_leaderboard(page, board["url"], board["name"])
                out_f.write(json.dumps(res, ensure_ascii=False) + "\n")
                out_f.flush()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
