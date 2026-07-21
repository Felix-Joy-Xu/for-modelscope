import json
import time
import requests
import random
from datetime import datetime, timezone

OUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_tencent_campus.jsonl"

def get_detail(session, post_id):
    url = f"https://join.qq.com/api/v1/position/getPositionDetail?postId={post_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://join.qq.com/post.html",
        "X-Requested-With": "XMLHttpRequest"
    }
    try:
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == 0:
                d = data.get("data", {})
                # 合并职位描述和要求
                return (d.get("responsibility", "") + "\n" + d.get("requirement", "")).strip()
        return ""
    except:
        return ""

def main():
    print("🚀 启动腾讯校招深度收割 (Plus Version)...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://join.qq.com/post.html"
    })
    
    total = 0
    seen = set()
    
    # 清理旧文件
    with open(OUT_FILE, "w", encoding="utf-8") as f: pass

    # 获取全量列表
    page = 1
    while True:
        url = "https://join.qq.com/api/v1/position/searchPosition"
        payload = {
            "projectIdList": [],
            "projectMappingIdList": [2, 104, 1, 14, 20, 5, 120, 114, 100], 
            "pageIndex": page,
            "pageSize": 50 
        }
        try:
            resp = session.post(url, json=payload, timeout=15)
            data = resp.json()
            if data.get("status") != 0: break
            
            pos_list = data.get("data", {}).get("positionList", [])
            if not pos_list: break
            
            for p in pos_list:
                post_id = str(p.get("postId"))
                if post_id in seen: continue
                seen.add(post_id)
                
                # --- 抓取详情 ---
                print(f"🔍 正在抓取详情 {post_id} | {p.get('positionTitle')}...", end="\r")
                jd_full = get_detail(session, post_id)
                
                record = {
                    "metadata": {
                        "platform": "tencent",
                        "crawl_timestamp": datetime.now(timezone.utc).isoformat(),
                        "job_id": post_id,
                        "is_campus": True,
                        "bg_name": p.get("bgs")
                    },
                    "basic_info": {
                        "job_title": p.get("positionTitle"),
                        "location": p.get("workCities"),
                        "recruit_type": p.get("projectName")
                    },
                    "requirements": {
                        "raw_jd_text": jd_full
                    }
                }
                with open(OUT_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1
                time.sleep(random.uniform(0.3, 0.6)) # 详情采样不要太快

            print(f"\n📦 已入库第 {page} 到第 {total} 条数据")
            page += 1
        except Exception as e:
            print(f"\n🛑 第 {page} 页列表拉取失败: {e}")
            break

    print(f"\n🏆 抓取完成！共计获取 {total} 条腾讯校招职位（含全量 JD）。")

if __name__ == "__main__":
    main()
