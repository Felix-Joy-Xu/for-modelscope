import json
import csv
import os

# 配置原始数据路径
RAW_JOBS_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs.jsonl"
RAW_CAMPUS_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus.jsonl"
OUTPUT_FILE = r"c:\Users\22735\Desktop\ai\data\out\bytedance_jobs_raw_organized.csv"

def convert_jsonl_to_csv(input_files, output_file):
    """
    直接将 JSONL 转换为 CSV，不进行去重和字段提取，仅做基础整理。
    """
    headers = [
        "job_id", "type", "title", "location", "category", 
        "crawl_timestamp", "raw_jd_text"
    ]
    
    count = 0
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        
        for file_path, job_type in input_files:
            if not os.path.exists(file_path):
                continue
                
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        item = json.loads(line)
                        meta = item.get("metadata", {})
                        basic = item.get("basic_info", {})
                        req = item.get("requirements", {})
                        
                        writer.writerow({
                            "job_id": meta.get("job_id", ""),
                            "type": job_type,
                            "title": basic.get("job_title", ""),
                            "location": "/".join(basic.get("location", [])),
                            "category": "/".join(basic.get("category_path", [])),
                            "crawl_timestamp": meta.get("crawl_timestamp", ""),
                            "raw_jd_text": req.get("raw_jd_text", "").replace('\n', ' ')
                        })
                        count += 1
                    except Exception:
                        continue
                        
    return count

if __name__ == "__main__":
    print("⏳ 正在按要求整理原始数据（无清洗）...")
    files_to_process = [
        (RAW_JOBS_FILE, "社招"),
        (RAW_CAMPUS_FILE, "校招")
    ]
    total_count = convert_jsonl_to_csv(files_to_process, OUTPUT_FILE)
    print(f"✅ 整理完成！")
    print(f"📊 共整理条目: {total_count}")
    print(f"📂 结果已保存至: {OUTPUT_FILE}")
