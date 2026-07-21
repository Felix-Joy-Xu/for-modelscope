import json
import re
from collections import Counter

def filter_coding_jobs(file_path):
    coding_keywords = ['python', 'java', 'go', 'c++', 'sql', 'shell', 'rust', '代码', '编程', '开发', 'coding', 'git']
    
    coding_jobs = []
    total = 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                total += 1
                basic = data.get('basic_info', {})
                jd = data.get('requirements', {}).get('raw_jd_text', '').lower()
                title = basic.get('job_title', '').lower()
                
                # 在标题或 JD 中查找代码关键词
                if any(kw in (title + jd) for kw in coding_keywords):
                    coding_jobs.append({
                        "job_id": data.get('metadata', {}).get('job_id'),
                        "title": basic.get('job_title'),
                        "category": basic.get('category_path', ['未知'])[0],
                        "location": basic.get('location', ['未知'])[0]
                    })
            except: continue
            
    return coding_jobs, total

if __name__ == "__main__":
    jobs, total = filter_coding_jobs(r'c:\Users\22735\Desktop\ai\data\out\jobs.jsonl')
    
    # 统计职类分布
    categories = Counter([j['category'] for j in jobs])
    
    results = {
        "total_analyzed": total,
        "coding_jobs_count": len(jobs),
        "coding_ratio": round(len(jobs) / total * 100, 2) if total else 0,
        "top_categories": dict(categories.most_common(10)),
        "samples": jobs[:15] # 展示前 15 个样本
    }
    print(json.dumps(results, ensure_ascii=False, indent=2))
