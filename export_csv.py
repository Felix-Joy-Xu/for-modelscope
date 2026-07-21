#!/usr/bin/env python3
"""将 MongoDB 中的 GitHub 数据导出为 CSV 文件"""
import csv
import os
from pymongo import MongoClient

OUTPUT_DIR = r"C:\Users\22735\Desktop\文献"
os.makedirs(OUTPUT_DIR, exist_ok=True)

c = MongoClient('mongodb://localhost:27017/coding_labor')
col = c['coding_labor']['raw_posts']

def export_to_csv(filter_query, filename, fields):
    """导出数据到 CSV"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    count = col.count_documents(filter_query)
    print(f"导出 {filename}: {count} 条数据...")
    
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for doc in col.find(filter_query).batch_size(500):
            row = {}
            for field in fields:
                if field == 'repo':
                    row[field] = doc.get('metadata', {}).get('repo', '')
                elif field == 'state':
                    row[field] = doc.get('metadata', {}).get('state', '')
                else:
                    row[field] = doc.get(field, '')
            writer.writerow(row)
    
    print(f"  ✓ 已保存到 {filepath}")
    return count

# ========== 1. 英文 Issue ==========
print("=" * 60)
print("导出英文 Issue 数据...")
print("=" * 60)
fields_issue = ['_id', 'title', 'text', 'url', 'created_at', 'phase', 'repo', 'state', 'anonymized_author']
total = export_to_csv(
    {'source': 'github_issue', 'lang': 'en'},
    'github_issues_en.csv',
    fields_issue
)

# ========== 2. 英文 Comment ==========
print("\n" + "=" * 60)
print("导出英文 Comment 数据...")
print("=" * 60)
fields_comment = ['_id', 'text', 'url', 'created_at', 'phase', 'anonymized_author']
total += export_to_csv(
    {'source': 'github_comment', 'lang': 'en'},
    'github_comments_en.csv',
    fields_comment
)

# ========== 3. 中文 Issue ==========
print("\n" + "=" * 60)
print("导出中文 Issue 数据...")
print("=" * 60)
total += export_to_csv(
    {'source': 'github_issue', 'lang': 'zh'},
    'github_issues_zh.csv',
    fields_issue
)

# ========== 4. 中文 Comment ==========
print("\n" + "=" * 60)
print("导出中文 Comment 数据...")
print("=" * 60)
total += export_to_csv(
    {'source': 'github_comment', 'lang': 'zh'},
    'github_comments_zh.csv',
    fields_comment
)

print("\n" + "=" * 60)
print(f"导出完成！共 {total} 条数据")
print(f"文件保存在: {OUTPUT_DIR}")
print("=" * 60)

c.close()
