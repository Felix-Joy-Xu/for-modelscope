import json
import time
import requests
import random
from datetime import datetime, timezone

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_tencent_campus.jsonl"

def fetch_page(page_index):
    url = "https://join.qq.com/api/v1/position/searchPosition"
    # 使用子智能体验证过的核心 ID
    payload = {
        "projectIdList": [],
        "projectMappingIdList": [2, 104, 1, 14, 20, 5], 
        "keyword": "",
        "bgList": [],
        "workCountryType": 0,
        "workCityList": [],
        "recruitCityList": [],
        "positionFidList": [],
        "pageIndex": page_index,
        "pageSize": 20
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://join.qq.com/post.html",
        "Origin": "https://join.qq.com",
        "Content-Type": "application/json;charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        # 使用 Session 保持长连接指纹
        session = requests.Session()
        resp = session.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        print(f"Page {page_index} error: HTTP {resp.status_code}")
        return None
    except Exception as e:
        print(f"Request error: {e}")
        return None

def main():
    print("🚀 启动腾讯校招全量收割 (Final Version)...")
    page = 1
    total = 0
    seen = set()
    
    # 先清理旧文件重新抓取
    with open(OUT_FILE, "w", encoding="utf-8") as f: pass

    while True:
        data = fetch_page(page)
        if not data or data.get("status") != 0:
            print(f"🛑 抓取在第 {page} 页中断。")
            break
            
        # 腾讯 API 的实际列表字段可能是 positionList 
        # 我们兼容处理不同的返回结构
        d = data.get("data") or {}
        pos_list = d.get("positionList") or d.get("list") or []
        
        if not pos_list:
            if page == 1:
                print("⚠️ 第一页即为空，请检查 ID 列表或是否被封。")
            else:
                print("✅ 已到达末尾。")
            break
            
        for p in pos_list:
            jid = str(p.get("postId") or p.get("id"))
            if jid in seen: continue
            seen.add(jid)
            
            record = {
                "metadata": {
                    "platform": "tencent",
                    "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                    "job_id": jid,
                    "is_campus": True,
                    "bg_name": p.get("bgs", [p.get("bgName")])[0] if p.get("bgs") else p.get("bgName")
                },
                "basic_info": {
                    "job_title": p.get("title") or p.get("name"),
                    "category_path": [p.get("categoryName")],
                    "location": p.get("workCityList", [p.get("workCityName")]),
                    "recruit_type": p.get("projectName")
                },
                "requirements": {
                    "raw_jd_text": p.get("desc", "") + "\n" + p.get("request", "")
                }
            }
            with open(OUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            total += 1
            
        print(f"📦 已入库第 {page} 页，累计: {total} 条")
        page += 1
        time.sleep(random.uniform(1, 3)) # 增加随机抖动规避 WAF

    print(f"🏆 抓取完成！共计获取 {total} 条腾讯校招职位。")

if __name__ == "__main__":
    main()
