#!/usr/bin/env python3
"""导出所有数据为 CSV"""
import csv
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/coding_labor')
db = client['coding_labor']
col = db['raw_posts']

# 按 source 导出
sources = ['github_discussion', 'github_issue', 'github_comment']

for source in sources:
    filename = f'github_{source.split("_")[1]}s_all.csv'
    print(f'Exporting {source} -> {filename}...')
    
    docs = col.find({'source': source}).sort('created_at', 1)
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['source', 'phase', 'lang', 'url', 'title', 'text', 
                        'created_at', 'author', 'repo', 'search_keyword', 
                        'comments_count', 'category'])
        
        count = 0
        for doc in docs:
            meta = doc.get('metadata', {}) or {}
            writer.writerow([
                doc.get('source', ''),
                doc.get('phase', ''),
                doc.get('lang', ''),
                doc.get('url', ''),
                doc.get('title', ''),
                doc.get('text', ''),
                doc.get('created_at', ''),
                doc.get('author', ''),
                meta.get('repo', ''),
                meta.get('search_keyword', ''),
                meta.get('comments_count', ''),
                meta.get('category', '')
            ])
            count += 1
        
        print(f'  Exported {count} rows')

print('Done!')
