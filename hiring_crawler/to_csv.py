import json
import csv
from pathlib import Path

jsonl_file = Path(r"D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl")
csv_file = Path(r"D:\hiring_data\boss_api\tech_jobs_25k_final.csv")

headers = [
    "jobName", "salaryDesc", "brandName", "cityName", "areaDistrict",
    "businessDistrict", "jobDegree", "jobExperience", "skills",
    "bossName", "bossTitle", "brandIndustry", "brandScaleName",
    "brandStageName", "crawl_ts"
]

count = 0
with open(jsonl_file, "r", encoding="utf-8") as fin, \
     open(csv_file, "w", encoding="utf-8-sig", newline="") as fout:
    
    writer = csv.writer(fout)
    writer.writerow(headers)
    
    for line in fin:
        if not line.strip(): continue
        try:
            data = json.loads(line)
            skills = " | ".join(data.get("skills", []))
            row = [
                data.get("jobName", ""),
                data.get("salaryDesc", ""),
                data.get("brandName", ""),
                data.get("cityName", ""),
                data.get("areaDistrict", ""),
                data.get("businessDistrict", ""),
                data.get("jobDegree", ""),
                data.get("jobExperience", ""),
                skills,
                data.get("bossName", ""),
                data.get("bossTitle", ""),
                data.get("brandIndustry", ""),
                data.get("brandScaleName", ""),
                data.get("brandStageName", ""),
                data.get("crawl_ts", "")
            ]
            writer.writerow(row)
            count += 1
        except Exception as e:
            continue

print(f"成功将 {count} 条数据导出至: {csv_file}")
