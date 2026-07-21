#!/usr/bin/env python3
"""修复掘金评论数据 - 从 API 重新获取评论内容"""
import time, random, hashlib, logging, json
from datetime import datetime, timezone
from pymongo import MongoClient, errors as mongo_errors
import requests

MONGO_URI = "mongodb://localhost:27017/coding_labor"
DB_NAME = "coding_labor"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db["raw_posts"]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
})

def insert(doc):
    url = doc.get("url", "")
    text_prefix = doc.get("text", "")[:100]
    doc_id = hashlib.sha256(f"{url}_{text_prefix}".encode()).hexdigest()
    doc["_id"] = doc_id
    doc["crawled_at"] = datetime.now(timezone.utc).isoformat()
    doc["version"] = "1.0"
    try:
        col.insert_one(doc)
        return True
    except mongo_errors.DuplicateKeyError:
        return True
    except Exception as e:
        logger.error(f"Insert error: {e}")
        return False

# 获取所有掘金文章 ID
articles = col.find({"source": "juejin_article"}, {"metadata.article_id": 1})
article_ids = list(set(a.get("metadata", {}).get("article_id", "") for a in articles if a.get("metadata", {}).get("article_id")))
logger.info(f"Found {len(article_ids)} articles to fetch comments for")

total_comments = 0
for i, article_id in enumerate(article_ids):
    if i % 10 == 0:
        logger.info(f"Progress: {i}/{len(article_ids)}, comments so far: {total_comments}")
    
    try:
        resp = session.post(
            'https://api.juejin.cn/interact_api/v1/comment/list',
            json={"item_id": article_id, "item_type": 2, "cursor": "0", "limit": 20},
            timeout=30
        )
        if resp.status_code != 200:
            continue
        data = resp.json()
        if data.get("err_no") != 0:
            continue
        
        for comment in data.get("data", []):
            comment_info = comment.get("comment_info", {})
            if not comment_info:
                continue
            
            # 字段名是 comment_content 不是 content
            content = comment_info.get("comment_content", "") or ""
            if not content:
                continue
            
            comment_id = comment_info.get("comment_id", "")
            # 用户名在 user_info 中
            user_info = comment.get("user_info", {})
            user_name = user_info.get("user_name", "") if user_info else ""
            
            comment_ts = comment_info.get("ctime", "0")
            if comment_ts:
                comment_str = datetime.fromtimestamp(int(comment_ts), tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                comment_str = ""
            
            doc = {
                "source": "juejin_comment",
                "phase": "B",
                "lang": "zh",
                "url": f"https://juejin.cn/post/{article_id}#comment-{comment_id}",
                "title": "",
                "text": content,
                "created_at": comment_str,
                "author": user_name,
                "metadata": {
                    "article_id": article_id,
                    "digg_count": comment_info.get("digg_count", 0),
                }
            }
            insert(doc)
            total_comments += 1
        
        time.sleep(random.uniform(0.5, 1.5))
    except Exception as e:
        logger.error(f"Error fetching comments for {article_id}: {e}")
        time.sleep(2)

logger.info(f"Total comments fetched: {total_comments}")

# 统计
total = col.count_documents({"source": "juejin_comment"})
logger.info(f"Total juejin comments in DB: {total}")
client.close()
