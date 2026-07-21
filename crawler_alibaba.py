import requests
import json
import time
import re
from datetime import datetime, timezone

OUT_FILE_CAMPUS = r"c:\Users\22735\Desktop\ai\data\out\jobs_alibaba_campus.jsonl"
OUT_FILE_SOCIAL = r"c:\Users\22735\Desktop\ai\data\out\jobs_alibaba_social.jsonl"

def get_csrf_and_cookie(url):
    """访问主页获取 CSRF Token 和必要的 Cookie"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    session = requests.Session()
    resp = session.get(url, headers=headers)
    # 尝试从 cookie 或 meta 标签中提取 _csrf
    csrf = session.cookies.get("_csrf")
    if not csrf:
        match = re.search(r'csrfToken\s*=\s*"([^"]+)"', resp.text)
        if match: csrf = match.group(1)
    return session, csrf

def fetch_alibaba_campus(session, csrf):
    print("🚀 启动阿里校招全量收割...")
    url = f"https://campus-talent.alibaba.com/position/search?_csrf={csrf}"
    # 阿里校招通常通过不同的 batchId 区分项目
    # 这里我们尝试通过不传 batchId 或循环常见 batchId 来获取
    batches = [
        {"id": 100000540002, "name": "2027届实习生"}, # 探测到的核心 ID
        {"id": 100000540001, "name": "日常实习"},
        {"id": 100000063002, "name": "研究型实习"},
        {"id": 100000540003, "name": "阿里星"}
    ]
    
    total_saved = 0
    with open(OUT_FILE_CAMPUS, "w", encoding="utf-8") as f: pass

    for batch in batches:
        page = 1
        print(f"📦 正在抓取批次: {batch['name']}...")
        while True:
            payload = {
                "batchId": batch["id"],
                "pageIndex": page,
                "pageSize": 20,
                "channel": "campus_group_official_site",
                "language": "zh"
            }
            try:
                resp = session.post(url, json=payload, timeout=10)
                data = resp.json()
                if data.get("code") != "200": break
                
                pos_list = data.get("data", {}).get("list", [])
                if not pos_list: break
                
                for p in pos_list:
                    record = {
                        "metadata": {
                            "platform": "alibaba",
                            "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                            "job_id": str(p.get("id")),
                            "is_campus": True,
                            "bg_name": p.get("deptName")
                        },
                        "basic_info": {
                            "job_title": p.get("name"),
                            "location": p.get("workAddress"),
                            "recruit_type": batch["name"]
                        },
                        "requirements": {
                            "raw_jd_text": (str(p.get("description", "")) + "\n" + str(p.get("requirement", ""))).strip()
                        }
                    }
                    with open(OUT_FILE_CAMPUS, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total_saved += 1
                
                page += 1
                time.sleep(1)
            except:
                break
    print(f"✅ 阿里校招抓取完成，共计 {total_saved} 条。")

def main():
    # 阿里校招
    session, csrf = get_csrf_and_cookie("https://campus-talent.alibaba.com/campus/position")
    if csrf:
        fetch_alibaba_campus(session, csrf)
    else:
        print("❌ 无法获取阿里 CSRF Token，请检查网络或策略。")

if __name__ == "__main__":
    main()
