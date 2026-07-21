#!/usr/bin/env python3
"""导出 Discussions 数据为 CSV"""
import csv
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/coding_labor')
db = client['coding_labor']
col = db['raw_posts']

# 导出 Discussions
with open('github_discussions.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['source', 'phase', 'lang', 'url', 'title', 'text', 'created_at', 'author', 'repo', 'category', 'comments_count', 'search_keyword'])
    
    for doc in col.find({'source': 'github_discussion'}).sort('created_at', -1):
        meta = doc.get('metadata', {})
        writer.writerow([
            doc.get('source', ''),
            doc.get('phase', ''),
            doc.get('lang', ''),
            doc.get('url', ''),
            doc.get('title', ''),
            doc.get('text', '')[:500],
            doc.get('created_at', ''),
            doc.get('author', ''),
            meta.get('repo', ''),
            meta.get('category', ''),
            meta.get('comments_count', 0),
            meta.get('search_keyword', '')
        ])

print("Discussions CSV exported!")

# 统计
total = col.count_documents({'source': 'github_discussion'})
print(f'Total discussions: {total}')

# 按仓库统计
pipeline = [
    {'$match': {'source': 'github_discussion'}},
    {'$group': {'_id': '$metadata.repo', 'count': {'$sum': 1}}},
    {'$sort': {'count': -1}}
]
print('\n按仓库统计:')
for r in col.aggregate(pipeline):
    print(f'  {r["_id"]}: {r["count"]}')

client.close()
