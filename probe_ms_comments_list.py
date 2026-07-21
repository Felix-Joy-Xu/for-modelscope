# -*- coding: utf-8 -*-
"""探测魔搭评论列表接口：打开模型页，点击评论 Tab，记录所有 XHR 请求。"""
import asyncio
import json
from playwright.async_api import async_playwright

MODEL = "iic/CosyVoice2-0.5B"  # 97 条评论的模型


async def main():
    seen = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        async def on_response(resp):
            u = resp.url.lower()
            if any(k in u for k in ("comment", "discussion", "issue", "pr", "reply")):
                if resp.request.resource_type in ("xhr", "fetch"):
                    try:
                        j = await resp.json()
                        keys = list(j.get("Data", {}).keys()) if isinstance(j.get("Data"), dict) else f"list[{len(j.get('Data') or [])}]"
                        seen.append((resp.status, resp.url, str(keys)[:200]))
                    except Exception:
                        seen.append((resp.status, resp.url, "(non-json)"))

        page.on("response", on_response)

        for url in [f"https://www.modelscope.cn/models/{MODEL}/summary",
                    f"https://www.modelscope.cn/models/{MODEL}/comments"]:
            print(">>>", url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)
                # 尝试点击评论/讨论相关 Tab
                for text in ["评论", "讨论", "Comment", "Discussion"]:
                    try:
                        el = page.get_by_text(text, exact=False).first
                        if await el.count() > 0:
                            await el.click(timeout=2000)
                            print("  点击了:", text)
                            await asyncio.sleep(4)
                    except Exception:
                        pass
                # 尝试翻页
                for text in ["下一页", ">", "2"]:
                    try:
                        el = page.get_by_text(text, exact=True).last
                        if await el.count() > 0:
                            await el.click(timeout=1500)
                            await asyncio.sleep(3)
                            break
                    except Exception:
                        pass
            except Exception as e:
                print("  页面错误:", e)

        await browser.close()

    print("\n=== 捕获到的相关 XHR ===")
    for s in seen:
        print(s)


if __name__ == "__main__":
    asyncio.run(main())
