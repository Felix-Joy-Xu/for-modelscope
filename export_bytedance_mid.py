import pandas as pd
import glob
import os
import json

RAW_DATA_PATH = r"..\bytedance_crawler\outputs"
OUTPUT_FILE = r"..\bytedance_crawler\outputs\bytedance_mid_platform_jobs.csv"

def export_mid_platform_jobs():
    files = glob.glob(os.path.join(RAW_DATA_PATH, "jobs_bytedance_*.jsonl"))
    results = []
    
    for f in files:
        basename = os.path.basename(f)
        track = basename.split("_")[2].replace(".jsonl", "")
        
        with open(f, 'r', encoding='utf-8') as file:
            for line in file:
                try:
                    data = json.loads(line)
                    title = data.get("basic_info", {}).get("job_title", "")
                    url = data.get("metadata", {}).get("url", "")
                    
                    if "中台" in title:
                        results.append({
                            "Job Title": title,
                            "Track": track,
                            "URL": url
                        })
                except:
                    continue
                    
    df = pd.DataFrame(results)
    if df.empty:
        print("未发现匹配的岗位。")
        return

    # To handle Chinese correctly in Excel, use utf-8-sig
    df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"成功导出 {len(df)} 个岗位到 {OUTPUT_FILE}")
    
    # Print a table for the user
    print("\n前 20 条记录预览:")
    print(df.head(20).to_markdown(index=False))

if __name__ == "__main__":
    export_mid_platform_jobs()
