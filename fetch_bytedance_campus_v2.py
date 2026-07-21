import requests
import json
import time
from datetime import datetime, timezone

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus_full.jsonl"
URL = "https://jobs.bytedance.com/api/v1/search/job/posts"

def fetch_all_campus_jobs():
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    payload = {
        "keyword": "",
        "limit": 100,
        "offset": 0,
        "portal_type": 3,
        "subject_id_list": [],
        "job_category_id_list": [],
        "location_code_list": []
    }
    
    all_jobs = {}
    total_count = None
    offset = 0
    limit = 100
    
    print("🚀 开始抓取字节跳动全量校招数据...")
    
    while True:
        payload["offset"] = offset
        payload["limit"] = limit
        
        try:
            response = requests.post(URL, json=payload, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"❌ 请求失败: {response.status_code}")
                break
            
            res_data = response.json().get("data", {})
            if total_count is None:
                total_count = res_data.get("count", 0)
                print(f"📊 官网显示总量: {total_count}")
            
            job_list = res_data.get("job_post_list", [])
            if not job_list:
                break
                
            for job in job_list:
                jid = str(job.get("id"))
                if jid not in all_jobs:
                    record = {
                        "metadata": {
                            "job_id": jid, 
                            "is_campus": True, 
                            "crawl_timestamp": datetime.now(timezone.utc).isoformat()
                        },
                        "basic_info": {
                            "job_title": job.get("title"),
                            "category_path": [job.get("job_category", {}).get("name")],
                            "location": [c.get("name") for c in (job.get("city_list") or [])]
                        },
                        "requirements": {
                            "raw_jd_text": (job.get("description") or "") + "\n" + (job.get("requirement") or "")
                        }
                    }
                    all_jobs[jid] = record
            
            print(f"✅ 已抓取: {offset + len(job_list)} / {total_count} (唯一 ID: {len(all_jobs)})")
            
            offset += len(job_list)
            if offset >= total_count or len(job_list) == 0:
                break
                
            time.sleep(0.5) # 友好的抓取频率
            
        except Exception as e:
            print(f"⚠️ 发生错误: {e}")
            break
            
    # 保存结果
    print(f"💾 正在保存 {len(all_jobs)} 条唯一记录...")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for record in all_jobs.values():
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
    print(f"✨ 抓取完成！数据已保存至: {OUT_FILE}")

if __name__ == "__main__":
    fetch_all_campus_jobs()
