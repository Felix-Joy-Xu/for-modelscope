import os
import json
import time
from modelscope.hub.api import HubApi
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(r"D:\国际比较政治经济学\01-爬虫程序")
MODELS_FILE = BASE_DIR / "modelscope_output" / "models_all.json"
OUTPUT_FILE = BASE_DIR / "modelscope_output" / "ms_model_dependencies.jsonl"
STATE_FILE = BASE_DIR / "modelscope_output" / "state_ms_trees.json"

def fetch_file_tree(api, model_id):
    """获取模型文件树结构和配置文件"""
    result = {"model_id": model_id, "status": "success", "crawled_at": time.time()}
    try:
        files = api.get_model_files(model_id=model_id, recursive=True)
        result["files"] = [{"Name": f.get("Name"), "Size": f.get("Size")} for f in files] if files else []
        
        # 判断依赖框架
        file_names = [f["Name"] for f in result["files"]]
        result["has_requirements"] = any("requirements.txt" in f for f in file_names)
        result["has_pytorch"] = any(f.endswith(".bin") or f.endswith(".pt") or f.endswith(".pth") for f in file_names)
        result["has_safetensors"] = any(f.endswith(".safetensors") for f in file_names)
        result["has_gguf"] = any(f.endswith(".gguf") for f in file_names)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result

def main():
    if not MODELS_FILE.exists():
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

    api = HubApi()
    
    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
        # SDK 请求，适当限并发防止被封
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_model = {executor.submit(fetch_file_tree, api, m_id): m_id for m_id in models_to_scrape}
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
