# -*- coding: utf-8 -*-
"""探测回复展开时触发的 XHR：打开评论页，点击"回复"相关元素。"""
import asyncio
from playwright.async_api import async_playwright

MODEL = "iic/CosyVoice2-0.5B"


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
            if "modelscope.cn/api" in u and resp.request.resource_type in ("xhr", "fetch"):
                if any(k in u for k in ("comment", "reply", "children", "discussion")):
                    try:
                        j = await resp.json()
                        d = j.get("Data")
                        info = list(d.keys()) if isinstance(d, dict) else f"list[{len(d or [])}]"
                        seen.append((resp.status, resp.url, str(info)[:150]))
                    except Exception:
                        seen.append((resp.status, resp.url, "(non-json)"))

        page.on("response", on_response)

        url = f"https://www.modelscope.cn/models/{MODEL}/comments"
        print(">>>", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(6)

        # 打印页面上所有包含"回复"的可点击元素文本
        try:
            els = await page.get_by_text("回复", exact=False).all()
            print(f"页面含'回复'元素 {len(els)} 个")
            for el in els[:5]:
                try:
                    txt = (await el.inner_text())[:40]
                    print("  -", txt.replace("\n", " "))
                except Exception:
                    pass
            # 逐个点"查看回复/共N条回复"类元素
            for el in els[:3]:
                try:
                    await el.click(timeout=2000)
                    print("  点击了一个'回复'元素")
                    await asyncio.sleep(3)
                except Exception:
                    pass
        except Exception as e:
            print("元素查找失败:", e)

        await browser.close()

    print("\n=== 捕获到的 API XHR ===")
    for s in seen:
        print(s)


if __name__ == "__main__":
    asyncio.run(main())
