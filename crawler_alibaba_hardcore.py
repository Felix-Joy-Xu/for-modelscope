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

# --- 注入从子智能体获取的最新凭证 ---
CSRF_TOKEN = "e4efa6e7-ab95-4454-b83d-e40b5c4df142"
COOKIE_STR = ALIBABA_COOKIE_STR

def fetch_campus():
    url = f"https://campus-talent.alibaba.com/position/search?_csrf={CSRF_TOKEN}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Cookie": COOKIE_STR,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "X-Csrf-Token": CSRF_TOKEN
    }
    
    batches = [
        {"id": 100000540002, "name": "2027届实习生"},
        {"id": 100000540001, "name": "日常实习"},
        {"id": 100000063002, "name": "研究型实习"},
        {"id": 100000540003, "name": "阿里星"}
    ]
    
    total = 0
    with open(OUT_FILE_CAMPUS, "w", encoding="utf-8") as f: pass

    for b in batches:
        print(f"📦 正在扫描: {b['name']}...")
        page = 1
        while True:
            payload = {
                "batchId": b["id"],
                "pageIndex": page,
                "pageSize": 50,
                "channel": "campus_group_official_site",
                "language": "zh"
            }
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                if resp.status_code != 200:
                    print(f"   ❌ HTTP {resp.status_code}: {resp.text[:100]}")
                    break
                data = resp.json()
                if page == 1:
                    print(f"   --- DEBUG: {str(data)[:200]}...")
                if str(data.get("code")) != "200": 
                    print(f"   ⚠️ API Error (Code {data.get('code')}): {data.get('message')}")
                    break
                
                pos = data.get("data", {}).get("list", [])
                if not pos: break
                
                for p in pos:
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
                            "recruit_type": b["name"]
                        },
                        "requirements": {
                            "raw_jd_text": (str(p.get("description", "")) + "\n" + str(p.get("requirement", ""))).strip()
                        }
                    }
                    with open(OUT_FILE_CAMPUS, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total += 1
                
                print(f"   已入库第 {page} 页，累计 {total} 条...", end="\r")
                page += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"   ❌ 网络错误: {e}")
                break
        print(f"\n✅ {b['name']} 完成。")

    print(f"\n🏆 阿里校招采集大获全胜！累计获取 {total} 条高精岗位。")

if __name__ == "__main__":
    fetch_campus()
