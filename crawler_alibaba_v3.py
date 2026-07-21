import os as _os
try:
    from _secrets import ALIBABA_COOKIE_STR
except ImportError:
    ALIBABA_COOKIE_STR = _os.environ.get("ALIBABA_COOKIE_STR", "")

import requests
import json
import time
from datetime import datetime, timezone

OUT_FILE_CAMPUS = r"c:\Users\22735\Desktop\ai\data\out\jobs_alibaba_campus.jsonl"

# --- 使用子智能体刚刚捕获的最新鲜活凭据 ---
CSRF_TOKEN = "e4efa6e7-ab95-4454-b83d-e40b5c4df142"
COOKIE_STR = ALIBABA_COOKIE_STR

def fetch_batch(batch_info):
    url = f"https://campus-talent.alibaba.com/position/search?_csrf={CSRF_TOKEN}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Cookie": COOKIE_STR,
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": f"https://campus-talent.alibaba.com/campus/position?batchId={batch_info['id']}",
        "X-Csrf-Token": CSRF_TOKEN
    }
    
    page = 1
    total = 0
    while True:
        payload = {
            "batchId": batch_info["id"],
            "pageIndex": page,
            "pageSize": 50,
            "channel": "campus_group_official_site",
            "language": "zh"
        }
        if batch_info.get("aliStar"):
            payload["aliStar"] = "Y"
            
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            data = resp.json()
            if not data.get("success"):
                print(f"   ⚠️ {batch_info['name']} 停止在第 {page} 页: {data.get('errorMsg')}")
                break
            
            p_data = data.get("data", {})
            pos_list = p_data.get("list", [])
            if not pos_list:
                break
            
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
                        "recruit_type": batch_info["name"]
                    },
                    "requirements": {
                        "raw_jd_text": (str(p.get("description", "")) + "\n" + str(p.get("requirement", ""))).strip()
                    }
                }
                with open(OUT_FILE_CAMPUS, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1
            
            print(f"   {batch_info['name']} | 第 {page} 页 | 累计 {total} 条", end="\r")
            page += 1
            time.sleep(1)
        except Exception as e:
            print(f"\n   ❌ Error: {e}")
            break
    print(f"\n✅ {batch_info['name']} 完成，共抓取 {total} 条。")
    return total

def main():
    batches = [
        {"id": 100000540002, "name": "2027届实习生"},
        {"id": 100000560002, "name": "日常实习生"},
        {"id": 100000560001, "name": "研究型实习生"},
        {"id": 100000540002, "name": "阿里星", "aliStar": True}
    ]
    
    with open(OUT_FILE_CAMPUS, "w", encoding="utf-8") as f: pass
    
    grand_total = 0
    for b in batches:
        grand_total += fetch_batch(b)
        
    print(f"\n🏆 阿里校招全量收割完毕！总计: {grand_total} 条。")

if __name__ == "__main__":
    main()
