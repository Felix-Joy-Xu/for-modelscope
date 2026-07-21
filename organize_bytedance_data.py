import json
import pandas as pd
import re
from pathlib import Path

# 定义输入输出路径
RAW_JOBS_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs.jsonl"
RAW_CAMPUS_FILE = r"c:\Users\22735\Desktop\ai\data\out\jobs_campus.jsonl"
OUTPUT_CSV = r"c:\Users\22735\Desktop\ai\data\out\bytedance_jobs_cleaned.csv"

# AI 关键词库 (保持与对比分析一致)
AI_KEYWORDS = [
    'AI', 'LLM', '大模型', 'GPT', 'Transformer', '生成式', 'AIGC', 
    '机器学习', '深度学习', '多模态', 'Multimodal', 'Agent', 
    'NLP', 'CV', '强化学习', 'RL', 'Stable Diffusion', 'PyTorch', 'TensorFlow'
]

def extract_requirements(text):
    """
    尝试从JD文本中提取学历和工作年限（简单启发式）
    """
    edu = "不限"
    if "本科及以上" in text or "本科以上" in text:
        edu = "本科"
    elif "硕士及以上" in text or "硕士以上" in text:
        edu = "硕士"
    elif "博士及以上" in text or "博士以上" in text:
        edu = "博士"
    
    # 提取年限 (如 3年以上, 5年及左右)
    exp = "不限"
    exp_match = re.search(r'(\d+)\s*(?:年|Yeares?)(?:以上|及以上|左右)', text)
    if exp_match:
        exp = f"{exp_match.group(1)}年+"
    
    return edu, exp

def process_file(path, recruit_type):
    if not Path(path).exists():
        print(f"Warning: {path} not found.")
        return []
        
    records = []
    seen_ids = set()
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
                job_id = item.get("metadata", {}).get("job_id")
                
                # 去重
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                
                basic = item.get("basic_info", {})
                reqs = item.get("requirements", {})
                jd_text = reqs.get("raw_jd_text", "")
                title = basic.get("job_title", "")
                
                # 标签提取
                combined_text = f"{title}\n{jd_text}"
                is_ai = any(kw.upper() in combined_text.upper() for kw in AI_KEYWORDS)
                
                # 学历年限补全
                edu, exp = extract_requirements(jd_text)
                
                records.append({
                    "job_id": job_id,
                    "type": recruit_type,
                    "title": title,
                    "category": "/".join(basic.get("category_path", ["未知"])),
                    "location": "/".join(basic.get("location", ["未知"])),
                    "publish_date": basic.get("publish_date"),
                    "is_ai": is_ai,
                    "education": edu,
                    "experience": exp,
                    "jd_snippet": jd_text[:200].replace("\n", " ") + "..." # 缩略图
                })
            except Exception as e:
                continue
    return records

def main():
    print("⏳ 开始整理字节跳动职位数据...")
    
    # 处理社招和校招
    social_records = process_file(RAW_JOBS_FILE, "社招")
    campus_records = process_file(RAW_CAMPUS_FILE, "校招")
    
    all_records = social_records + campus_records
    df = pd.DataFrame(all_records)
    
    # 保存结果
    df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    
    print(f"✅ 整理完成！")
    print(f"📊 统计摘要：")
    print(f"- 总岗位数 (去重后): {len(df)}")
    print(df.groupby(['type', 'is_ai']).size().unstack(fill_value=0))
    print(f"\n📂 结果已保存至: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
