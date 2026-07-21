import os
import json
import asyncio
from playwright.async_api import async_playwright
import time
from pathlib import Path

# 设置路径
BASE_DIR = Path(r"D:\国际比较政治经济学\01-爬虫程序")
MODELS_FILE = BASE_DIR / "modelscope_output" / "models_all.json"
OUTPUT_FILE = BASE_DIR / "modelscope_output" / "ms_comments_all.jsonl"
STATE_FILE = BASE_DIR / "modelscope_output" / "state_ms_comments.json"

async def scrape_comments_for_model(page, model_id):
    """访问模型主页，等待评论/讨论版块加载并抓取相关内容"""
    url = f"https://www.modelscope.cn/models/{model_id}/summary"
    comments_data = []

    # 监听 XHR 响应
    async def handle_response(response):
        if "comment" in response.url.lower() or "discussion" in response.url.lower():
            if response.request.resource_type in ["xhr", "fetch"]:
                try:
                    data = await response.json()
                    comments_data.append({
                        "url": response.url,
                        "data": data
                    })
                except Exception:
                    pass

    page.on("response", handle_response)

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        # 尝试点击“评论”或“讨论”Tab (如果有的话)
        # 这里使用比较通用的等待策略
        await asyncio.sleep(3)
        
        # 尝试提取页面内直接可见的文本（作为后备方案）
        page_content = await page.content()
        return {
            "model_id": model_id,
            "api_intercepts": comments_data,
            "status": "success",
            "crawled_at": time.time()
        }
    except Exception as e:
        return {
            "model_id": model_id,
            "status": "error",
            "error": str(e),
            "crawled_at": time.time()
        }
    finally:
        page.remove_listener("response", handle_response)

async def main():
    if not MODELS_FILE.exists():
        print(f"File not found: {MODELS_FILE}")
        return

    with open(MODELS_FILE, "r", encoding="utf-8") as f:
        models = json.load(f)
    
    # 按照下载量排序，优先爬取高下载量模型
    models.sort(key=lambda x: x.get("Downloads", 0), reverse=True)
    
    # 加载已完成状态
    completed = set()
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            completed = set(json.load(f))
    
    print(f"Total models: {len(models)}, Completed: {len(completed)}, Remaining: {len(models) - len(completed)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
            for i, model in enumerate(models):
                model_id = model.get("Id")
                if not model_id or model_id in completed:
                    continue

                print(f"[{i+1}/{len(models)}] Scraping comments for: {model_id} ...")
                result = await scrape_comments_for_model(page, model_id)
                
                out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_f.flush()
                
                completed.add(model_id)
                with open(STATE_FILE, "w") as sf:
                    json.dump(list(completed), sf)
                
                await asyncio.sleep(1) # 防封禁延迟

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
