import json
import time
import os
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_alibaba_campus.jsonl"

def crawl_alibaba():
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    
    with sync_playwright() as p:
        print("🚀 启动深度拟人爬虫 (结构适配版)...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()
        
        seen_ids = set()
        
        def handle_response(response):
            if "position/search" in response.url.lower():
                try:
                    if response.request.method == "POST":
                        data = response.json()
                        # 根据最新抓包结果适配结构: content -> datas
                        content = data.get("content", {})
                        pos_list = content.get("datas", [])
                        
                        # 兼容旧版或其他可能的结构
                        if not pos_list:
                            pos_list = data.get("data", {}).get("list", [])
                        
                        if pos_list:
                            added = 0
                            for pj in pos_list:
                                jid = str(pj.get("id"))
                                if jid not in seen_ids:
                                    seen_ids.add(jid)
                                    item = {
                                        "metadata": {
                                            "platform": "alibaba",
                                            "job_id": jid,
                                            "is_campus": True,
                                            "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                                            "bg_name": pj.get("deptName") or "/".join(pj.get("circleNames", []))
                                        },
                                        "basic_info": {
                                            "job_title": pj.get("name"),
                                            "location": "/".join(pj.get("workLocations", [])),
                                            "recruit_type": pj.get("batchName") or "阿里校招"
                                        },
                                        "requirements": {
                                            "raw_jd_text": (str(pj.get("description", "")) + "\n" + str(pj.get("requirement", ""))).strip()
                                        }
                                    }
                                    with open(OUT_FILE, "a", encoding="utf-8") as f:
                                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                                    added += 1
                            if added > 0:
                                print(f"📡 API 成功解析: 本页新增 {added} 条 (当前累计: {len(seen_ids)})")
                except Exception as e:
                    # print(f"  [Error] {e}")
                    pass

        page.on("response", handle_response)

        print("🌐 正在连接阿里巴巴校招官网...")
        page.goto("https://campus-talent.alibaba.com/campus/position", wait_until="networkidle")
        page.wait_for_timeout(4000)

        # 清空
        with open(OUT_FILE, "w", encoding="utf-8") as f: pass

        # 更新标签库
        batch_labels = [
            "阿里巴巴2027届实习生",
            "阿里巴巴日常实习生",
            "阿里巴巴研究型实习生",
            "阿里星-27届实习生"
        ]

        for bf in batch_labels:
            print(f"\n🖱️ 正在处理项目: {bf}")
            try:
                target = page.locator(f"text={bf}").first
                if target.is_visible():
                    target.scroll_into_view_if_needed()
                    target.click(force=True)
                    print(f"   ✅ 已激活过滤器: {bf}")
                    page.wait_for_timeout(4000)
                    
                    # 开始逐页翻动
                    for p_num in range(1, 100):
                        print(f"   📄 Page {p_num} (已入库 {len(seen_ids)})...")
                        
                        # 翻页前稍作停留模拟真人阅读
                        time.sleep(1)
                        
                        # 下一页按钮
                        nxt = page.locator("button.next-pagination-item.next-next, [aria-label='下一页']").first
                        
                        if nxt.is_visible():
                            # 查禁状态
                            is_off = nxt.get_attribute("disabled") is not None or "disabled" in (nxt.get_attribute("class") or "")
                            if is_off:
                                print(f"   🏁 {bf} 扫描完毕。")
                                break
                            
                            nxt.click()
                            page.wait_for_timeout(3500)
                        else:
                            print(f"   🏁 未发现更多分页，结束本项扫描。")
                            break
                else:
                    print(f"   ⚠️ 找不到选项: {bf}")
            except Exception as e:
                print(f"   ❌ 批次处理遇到错误: {e}")

        print(f"\n🏆 采集大功告成！全量入库 {len(seen_ids)} 条高质量岗位数据。")
        browser.close()

if __name__ == "__main__":
    crawl_alibaba()
