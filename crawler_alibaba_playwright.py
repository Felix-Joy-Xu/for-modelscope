import json
import time
from playwright.sync_api import sync_playwright
from datetime import datetime, timezone

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_alibaba_campus.jsonl"

def crawl_alibaba():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 伪装成正常 Windows Chrome
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        print("🔗 正在加载阿里校招首页，激活会话环境...")
        page.goto("https://campus-talent.alibaba.com/campus/position")
        page.wait_for_timeout(5000) # 等待安全指纹加载并稳定

        # 获取 CSRF
        cookies = context.cookies()
        csrf = next((c['value'] for c in cookies if c['name'] == 'XSRF-TOKEN'), None)
        if not csrf:
            print("❌ 获取 XSRF-TOKEN 失败")
            return

        print(f"🔑 获取到临时令牌: {csrf[:10]}...")

        batches = [
            {"id": 100000540002, "name": "2027届实习生"},
            {"id": 100000560002, "name": "日常实习生"},
            {"id": 100000560001, "name": "研究型实习生"}
        ]
        
        with open(OUT_FILE, "w", encoding="utf-8") as f: pass
        total = 0

        for b in batches:
            print(f"📦 正在通过浏览器内核抓取 {b['name']}...")
            current_page = 1
            while True:
                # 在浏览器环境下直接请求 API
                result = page.evaluate(f"""
                    async () => {{
                        const response = await fetch('/position/search?_csrf={csrf}', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json;charset=UTF-8' }},
                            body: JSON.stringify({{
                                batchId: {b['id']},
                                pageIndex: {current_page},
                                pageSize: 20,
                                channel: 'campus_group_official_site',
                                language: 'zh'
                            }})
                        }});
                        return await response.json();
                    }}
                """)
                
                if not result.get("success") or not result.get("data", {}).get("list"):
                    print(f"   ⚠️ 第 {current_page} 页无数据，批次结束。")
                    break
                
                pos_list = result["data"]["list"]
                for p in pos_list:
                    item = {
                        "metadata": {
                            "platform": "alibaba",
                            "job_id": str(p.get("id")),
                            "is_campus": True,
                            "bg_name": p.get("deptName")
                        },
                        "basic_info": {
                            "job_title": p.get("name"),
                            "location": p.get("workAddress"),
                            "recruit_type": b["name"]
                        },
                        "requirements": {
                            "raw_jd_text": (str(p.get("description", "")) + "\n" + str(p.get("requirement", ""))).strip()
                        }
                    }
                    with open(OUT_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                    total += 1
                
                print(f"   已抓取第 {current_page} 页...", end="\r")
                current_page += 1
                time.sleep(1)

        print(f"\n🏆 阿里校招全量同步完成！共计: {total} 条。")
        browser.close()

if __name__ == "__main__":
    crawl_alibaba()
