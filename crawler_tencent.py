import asyncio
import json
import time
import random
import requests
from pathlib import Path
from datetime import datetime, timezone

# --- 配置 ---
OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_tencent.jsonl"
STATE_FILE = r"c:\Users\22735\Desktop\ai\data\state\state_tencent.json"

def save_record(record):
    with open(OUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def fetch_tencent_social(page_index=1, page_size=50):
    timestamp = int(time.time() * 1000)
    url = f"https://careers.tencent.com/tencentcareer/api/post/Query?timestamp={timestamp}&countryId=&cityId=&bgIds=&productId=&categoryId=&parentCategoryId=&attrId=&keyword=&pageIndex={page_index}&pageSize={page_size}&language=zh-cn&area=cn"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://careers.tencent.com/search.html"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        return resp.json()
    except Exception as e:
        print(f"Error fetching page {page_index}: {e}")
        return None

def crawl_all_social():
    print("开始抓取腾讯社招数据...")
    page = 1
    total_count = 0
    seen_ids = set()
    
    while True:
        data = fetch_tencent_social(page_index=page, page_size=100)
        if not data or data.get("Code") != 200:
            print(f"抓取中断或结束于第 {page} 页")
            break
            
        posts = (data.get("Data") or {}).get("Posts") or []
        if not posts:
            print("没有更多职位了。")
            break
            
        for p in posts:
            jid = str(p.get("PostId"))
            if jid in seen_ids: continue
            seen_ids.add(jid)
            
            # 详情通常需要再次请求或直接从列表页获取简版
            # 腾讯列表页包含：RecruitPostName, LocationName, CategoryName, BGName, LastUpdateTime, Responsibility
            record = {
                "metadata": {
                    "platform": "tencent",
                    "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                    "job_id": jid,
                    "bg_name": p.get("BGName")
                },
                "basic_info": {
                    "job_title": p.get("RecruitPostName"),
                    "category_path": [p.get("CategoryName")],
                    "location": [p.get("LocationName")],
                    "publish_date": p.get("LastUpdateTime"),
                },
                "requirements": {
                    "raw_jd_text": p.get("Responsibility") # 注意：列表页只有职责，详细 Requirement 需详情页
                }
            }
            save_record(record)
            total_count += 1
            
        print(f"已处理第 {page} 页，累计抓取: {total_count} 条")
        page += 1
        time.sleep(random.uniform(0.5, 1.5))
        
        # 腾讯通常有几百页
        if page > 500: break 

    return total_count

if __name__ == "__main__":
    count = crawl_all_social()
    print(f"腾讯社招抓取完成！共计: {count} 条")
