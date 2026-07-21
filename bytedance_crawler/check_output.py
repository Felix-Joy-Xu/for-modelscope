"""验证最终数据质量."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\22735\Desktop\bytedance_crawler\outputs\jobs_bytedance_experienced.jsonl"
with open(path, encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total: {len(lines)} records\n")
for i, line in enumerate(lines, 1):
    d = json.loads(line)
    m = d["metadata"]
    b = d["basic_info"]
    print(f"[{i}] {b['job_title']}")
    print(f"    ID:       {m['job_id']}")
    print(f"    URL:      {m['url']}")
    print(f"    Category: {b['category_path']} / {b['category_en_path']}")
    print(f"    Location: {b['location']}")
    print(f"    Date:     {b['publish_date']}")
    print()
