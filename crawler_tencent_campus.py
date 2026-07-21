import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

# --- 配置 ---
OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_tencent_campus.jsonl"

def save_record(record):
    with open(OUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def fetch_tencent_campus(page_index=1):
    url = "https://join.qq.com/api/v1/position/searchPosition"
    payload = {
        "projectIdList": [],
        "projectMappingIdList": [2, 104, 1, 14, 20, 5, 120, 114, 100], # 注入子智能体发现的完整项目 ID
        "keyword": "",
        "bgList": [],
        "workCountryType": 0,
        "workCityList": [],
        "recruitCityList": [],
        "positionFidList": [],
        "pageIndex": page_index,
        "pageSize": 100 # 加速采集
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://join.qq.com/post.html",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Debug: Status Code {resp.status_code}")
        data = resp.json()
        print(f"Debug: Response Structure: {list(data.keys()) if data else 'Empty'}")
        return data
    except Exception as e:
        print(f"Error fetching campus page {page_index}: {e}")
        return None

def crawl_all_campus():
    print("开始抓取腾讯校招数据...")
    page = 1
    total_count = 0
    seen_ids = set()
    
    while True:
        data = fetch_tencent_campus(page_index=page)
        if not data or data.get("status") != 0:
            print(f"抓取中断/结束于第 {page} 页")
            break
            
        res_data = data.get("data")
        pos_list = []
        if isinstance(res_data, list):
            pos_list = res_data
        elif isinstance(res_data, dict):
            pos_list = res_data.get("list") or []
            
        if not pos_list:
            print("没有更多校招职位了。")
            break
            
        for p in pos_list:
            jid = str(p.get("id"))
            if jid in seen_ids: continue
            seen_ids.add(jid)
            
            record = {
                "metadata": {
                    "platform": "tencent",
                    "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                    "job_id": jid,
                    "is_campus": True
                },
                "basic_info": {
                    "job_title": p.get("name"),
                    "category_path": [p.get("categoryName")],
                    "location": [p.get("workCityName")],
                    "bg_name": p.get("bgName")
                },
                "requirements": {
                    "raw_jd_text": (p.get("description") or "") + "\n" + (p.get("requirement") or "")
                }
            }
            save_record(record)
            total_count += 1
            
        print(f"已处理第 {page} 页，累计抓取: {total_count} 条")
        page += 1
        time.sleep(1)

    return total_count

if __name__ == "__main__":
    count = crawl_all_campus()
    print(f"腾讯校招抓取完成！共计: {count} 条")
