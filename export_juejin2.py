#!/usr/bin/env python3
"""导出掘金数据到 CSV - 修复版"""
import csv, json
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/coding_labor"
DB_NAME = "coding_labor"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db["raw_posts"]

# 查看一条评论的数据结构
sample = col.find_one({"source": "juejin_comment"})
if sample:
    print("Sample comment keys:", list(sample.keys()))
    print("Sample comment:", json.dumps(sample, ensure_ascii=False, indent=2)[:500])

# 查看一条文章的数据结构
sample_a = col.find_one({"source": "juejin_article"})
if sample_a:
    print("\nSample article keys:", list(sample_a.keys()))
    print("Sample article metadata:", json.dumps(sample_a.get("metadata", {}), ensure_ascii=False, indent=2)[:300])

client.close()
