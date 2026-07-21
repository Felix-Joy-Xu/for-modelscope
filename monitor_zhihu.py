#!/usr/bin/env python3
"""监控知乎爬虫进度"""
import time
from datetime import datetime
from pymongo import MongoClient

c = MongoClient('mongodb://localhost:27017/')
db = c['coding_labor']

for i in range(120):
    s = db.zhihu_search.count_documents({})
    cm = db.zhihu_comments.count_documents({})
    now = datetime.now().strftime('%H:%M:%S')
    print(f'[{now}] 内容:{s} 评论:{cm}')
    time.sleep(15)
