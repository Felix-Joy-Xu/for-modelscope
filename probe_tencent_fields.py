import requests
import json

def probe():
    url = "https://join.qq.com/api/v1/position/searchPosition"
    payload = {
        "projectIdList": [],
        "projectMappingIdList": [2, 104, 1, 14, 20, 5], 
        "keyword": "",
        "pageIndex": 1,
        "pageSize": 5
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://join.qq.com/post.html",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json;charset=UTF-8"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # 关键：打印第一条数据的完整键值对
            pos_list = data.get("data", {}).get("positionList", [])
            if pos_list:
                print("--- 🔍 探测到单条职位原始结构 ---")
                print(json.dumps(pos_list[0], indent=2, ensure_ascii=False))
            else:
                print("⚠️ positionList 为空，请确认 payload 字段。")
                print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"HTTP Error: {resp.status_code}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    probe()
