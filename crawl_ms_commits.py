import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

import os
import json
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 设置路径
BASE_DIR = Path(r"D:\国际比较政治经济学\01-爬虫程序")
MODELS_FILE = BASE_DIR / "modelscope_output" / "models_all.json"
OUTPUT_FILE = BASE_DIR / "modelscope_output" / "ms_commit_history.jsonl"
STATE_FILE = BASE_DIR / "modelscope_output" / "state_ms_commits.json"

TOKEN = MODELSCOPE_TOKEN
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Cookie": f"token={TOKEN}; ms_token={TOKEN}"
}

def fetch_commits(model_id):
    """获取模型的分支和版本历史"""
    url_branches = f"https://www.modelscope.cn/api/v1/models/{model_id}/branches"
    url_revisions = f"https://www.modelscope.cn/api/v1/models/{model_id}/revisions"
    
    result = {"model_id": model_id, "status": "success", "crawled_at": time.time()}
    try:
        r_b = requests.get(url_branches, headers=HEADERS, timeout=10)
        if r_b.status_code == 200:
            result["branches_data"] = r_b.json().get("Data", {})
            
        r_r = requests.get(url_revisions, headers=HEADERS, timeout=10)
        if r_r.status_code == 200:
            result["revisions_data"] = r_r.json().get("Data", {})
            
        if r_b.status_code != 200 and r_r.status_code != 200:
            result["status"] = "error"
            result["error"] = f"HTTP {r_b.status_code} / {r_r.status_code}"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result

def main():
    if not MODELS_FILE.exists():
        print(f"File not found: {MODELS_FILE}")
        return

    with open(MODELS_FILE, "r", encoding="utf-8") as f:
        models = json.load(f)
    
    models.sort(key=lambda x: x.get("Downloads", 0), reverse=True)
    
    completed = set()
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            completed = set(json.load(f))
            
    models_to_scrape = [m.get("Id") for m in models if m.get("Id") and m.get("Id") not in completed]
    print(f"Total models: {len(models)}, Completed: {len(completed)}, Remaining: {len(models_to_scrape)}")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
        # 使用较多线程因为是纯 API 请求
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_model = {executor.submit(fetch_commits, m_id): m_id for m_id in models_to_scrape}
            for i, future in enumerate(as_completed(future_to_model)):
                m_id = future_to_model[future]
                try:
                    res = future.result()
                    out_f.write(json.dumps(res, ensure_ascii=False) + "\n")
                    out_f.flush()
                    completed.add(m_id)
                    
                    if i % 10 == 0:
                        print(f"Progress: {i}/{len(models_to_scrape)} ({m_id})")
                        with open(STATE_FILE, "w") as sf:
                            json.dump(list(completed), sf)
                except Exception as e:
                    print(f"Error on {m_id}: {e}")

if __name__ == "__main__":
    main()
