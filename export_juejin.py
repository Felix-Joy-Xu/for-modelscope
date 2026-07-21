#!/usr/bin/env python3
"""导出掘金数据到 CSV"""
import csv, os
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/coding_labor"
DB_NAME = "coding_labor"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db["raw_posts"]

# 导出掘金文章
articles = list(col.find({"source": "juejin_article"}))
print(f"掘金文章: {len(articles)}")

with open("juejin_articles.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["phase", "title", "text", "created_at", "author", "url",
                 "search_keyword", "view_count", "digg_count", "comment_count"])
    for a in articles:
        meta = a.get("metadata", {})
        w.writerow([
            a.get("phase", ""),
            a.get("title", ""),
            a.get("text", "")[:500],
            a.get("created_at", ""),
            a.get("author", ""),
            a.get("url", ""),
            meta.get("search_keyword", ""),
            meta.get("view_count", 0),
            meta.get("digg_count", 0),
            meta.get("comment_count", 0),
        ])

# 导出掘金评论
comments = list(col.find({"source": "juejin_comment"}))
print(f"掘金评论: {len(comments)}")

with open("juejin_comments.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["phase", "text", "created_at", "author", "url",
                 "article_title", "search_keyword", "digg_count"])
    for c in comments:
        meta = c.get("metadata", {})
        w.writerow([
            c.get("phase", ""),
            c.get("text", ""),
            c.get("created_at", ""),
            c.get("author", ""),
            c.get("url", ""),
            meta.get("article_title", ""),
            meta.get("search_keyword", ""),
            meta.get("digg_count", 0),
        ])

# 统计
phase_a_articles = sum(1 for a in articles if a.get("phase") == "A")
phase_b_articles = sum(1 for a in articles if a.get("phase") == "B")
phase_a_comments = sum(1 for c in comments if c.get("phase") == "A")
phase_b_comments = sum(1 for c in comments if c.get("phase") == "B")

print(f"\n掘金文章: A={phase_a_articles}, B={phase_b_articles}")
print(f"掘金评论: A={phase_a_comments}, B={phase_b_comments}")
print(f"掘金总计: {len(articles) + len(comments)}")

client.close()
