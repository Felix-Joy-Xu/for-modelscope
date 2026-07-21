import asyncio
from playwright.async_api import async_playwright
import json
import sys

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        api_info = {}

        # 监听所有响应
        async def handle_response(response):
            if "comment" in response.url.lower() or "discussion" in response.url.lower():
                print(f"Found related URL: {response.url}")
                try:
                    data = await response.json()
                    print(f"Data keys: {data.keys()}")
                    if data.get("Data"):
                        print("SUCCESS! Found the API.")
                        api_info["url"] = response.url
                        api_info["request_headers"] = response.request.headers
                except Exception as e:
                    pass

        page.on("response", handle_response)
        
        print("Navigating to Qwen2.5-7B-Instruct...")
        # 去一个评论比较多的热门模型页面
        await page.goto("https://www.modelscope.cn/models/Qwen/Qwen2.5-7B-Instruct/summary", wait_until="networkidle")
        
        # 等待一下看看有没有评论加载
        await asyncio.sleep(5)
        
        await browser.close()
        
        if api_info:
            with open("ms_comment_api_info.json", "w", encoding="utf-8") as f:
                json.dump(api_info, f, ensure_ascii=False, indent=2)
            print("API info saved to ms_comment_api_info.json")
        else:
            print("No comment API intercepted.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
