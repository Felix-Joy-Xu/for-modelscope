import os as _os
try:
    from _secrets import ZHIHU_COOKIE_RAW
except ImportError:
    ZHIHU_COOKIE_RAW = _os.environ.get("ZHIHU_COOKIE_RAW", "")

#!/usr/bin/env python3
"""
知乎搜索爬虫 - 基于 Cookie 认证的 API 版本
功能：
1. 多关键词搜索（AI编程、人工智能、机器学习、深度学习、大模型等）
2. 分页获取全部结果
3. 爬取每个回答/文章下的评论
4. 存储到 MongoDB
5. 导出为 CSV
6. 断点续爬
"""
import requests
import json
import time
import csv
import os
from datetime import datetime
from urllib.parse import quote
from pymongo import MongoClient, ASCENDING

# ============ 配置 ============
MONGO_URI = 'mongodb://localhost:27017/'
MONGO_DB = 'coding_labor'
MONGO_COLLECTION = 'zhihu_search'
MONGO_COMMENTS_COLLECTION = 'zhihu_comments'

# Cookie（从浏览器复制）
COOKIE_RAW = ZHIHU_COOKIE_RAW

# 搜索关键词
KEYWORDS = [
    'AI编程', '人工智能', '机器学习', '深度学习', '大模型',
    'AI', 'ChatGPT', '大语言模型', '自然语言处理', '计算机视觉',
    '强化学习', '神经网络', 'Transformer', '扩散模型', 'AI绘画',
    'AI写作', 'AI视频', 'AI音乐', 'AI Agent', 'RAG',
    'Fine-tuning', 'Prompt Engineering', 'AI安全', 'AI伦理', 'AI就业',
]

# 请求间隔（秒）
REQUEST_INTERVAL = 1.5
MAX_RETRIES = 3
PAGE_SIZE = 20
MAX_PAGES = 50
COMMENT_PAGES = 5  # 每个回答/文章最多爬取5页评论（最多100条）

# ============ Cookie 编码 ============
def encode_cookie(cookie_str):
    parts = []
    for part in cookie_str.split('; '):
        if '=' in part:
            key, value = part.split('=', 1)
            try:
                value.encode('latin-1')
            except UnicodeEncodeError:
                value = quote(value)
        parts.append(f"{key}={value}")
    return '; '.join(parts)

COOKIE = encode_cookie(COOKIE_RAW)

# ============ MongoDB ============
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
collection = db[MONGO_COLLECTION]
comments_collection = db[MONGO_COMMENTS_COLLECTION]

# 创建索引
collection.create_index([('unique_id', ASCENDING)], unique=True)
collection.create_index([('keyword', ASCENDING)])
collection.create_index([('type', ASCENDING)])
collection.create_index([('created_time', ASCENDING)])

comments_collection.create_index([('comment_id', ASCENDING)], unique=True)
comments_collection.create_index([('parent_unique_id', ASCENDING)])
comments_collection.create_index([('parent_type', ASCENDING)])

# ============ 进度文件 ============
PROGRESS_FILE = os.path.join(os.path.dirname(__file__), 'zhihu_progress.json')

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

# ============ 请求头 ============
def make_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Origin': 'https://www.zhihu.com',
        'Cookie': COOKIE,
        'x-requested-with': 'fetch',
    }

# ============ 搜索 API ============
def search_zhihu(query, offset=0):
    headers = make_headers()
    headers['Referer'] = 'https://www.zhihu.com/search?type=content&q=' + quote(query)
    
    url = 'https://www.zhihu.com/api/v4/search_v3'
    params = {
        't': 'general',
        'q': query,
        'correction': '1',
        'offset': str(offset),
        'limit': str(PAGE_SIZE),
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"      限流，等待 {wait} 秒...")
                time.sleep(wait)
            else:
                print(f"      状态码: {resp.status_code}, 重试 {attempt+1}/{MAX_RETRIES}")
                time.sleep(3)
        except Exception as e:
            print(f"      请求异常: {e}, 重试 {attempt+1}/{MAX_RETRIES}")
            time.sleep(5)
    return None

# ============ 评论 API ============
def get_answer_comments(answer_id, offset=0, limit=20):
    """获取回答的评论"""
    url = f'https://www.zhihu.com/api/v4/answers/{answer_id}/comments'
    params = {'limit': str(limit), 'offset': str(offset), 'order': 'normal'}
    
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=make_headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
            else:
                time.sleep(3)
        except Exception as e:
            time.sleep(5)
    return None

def get_article_comments(article_id, offset=0, limit=20):
    """获取文章的评论"""
    url = f'https://www.zhihu.com/api/v4/articles/{article_id}/comments'
    params = {'limit': str(limit), 'offset': str(offset)}
    
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=make_headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
            else:
                time.sleep(3)
        except Exception as e:
            time.sleep(5)
    return None

# ============ 数据提取 ============
def extract_items(data, keyword):
    """提取搜索结果中的有效内容"""
    items = []
    for item in data.get('data', []):
        item_type = item.get('type', '')
        
        if item_type == 'search_result':
            obj = item.get('object', {})
            obj_type = obj.get('type', '')
            
            if obj_type == 'answer':
                question = obj.get('question', {})
                author = obj.get('author', {}) or {}
                unique_id = f"answer_{obj.get('id')}"
                items.append({
                    'unique_id': unique_id,
                    'keyword': keyword,
                    'type': 'answer',
                    'question_id': question.get('id'),
                    'question_title': question.get('title'),
                    'answer_id': obj.get('id'),
                    'content': obj.get('content', '') or '',
                    'voteup_count': obj.get('voteup_count', 0),
                    'comment_count': obj.get('comment_count', 0),
                    'created_time': obj.get('created_time'),
                    'updated_time': obj.get('updated_time'),
                    'author_name': author.get('name', ''),
                    'author_url': author.get('url', ''),
                    'author_headline': author.get('headline', ''),
                    'url': f"https://www.zhihu.com/question/{question.get('id')}/answer/{obj.get('id')}" 
                           if question.get('id') and obj.get('id') else '',
                    'crawl_time': datetime.now().isoformat(),
                })
            elif obj_type == 'article':
                author = obj.get('author', {}) or {}
                unique_id = f"article_{obj.get('id')}"
                items.append({
                    'unique_id': unique_id,
                    'keyword': keyword,
                    'type': 'article',
                    'article_id': obj.get('id'),
                    'title': obj.get('title'),
                    'content': obj.get('content', '') or '',
                    'excerpt': obj.get('excerpt', '') or '',
                    'voteup_count': obj.get('voteup_count', 0),
                    'comment_count': obj.get('comment_count', 0),
                    'created_time': obj.get('created'),
                    'updated_time': obj.get('updated'),
                    'author_name': author.get('name', ''),
                    'author_url': author.get('url', ''),
                    'author_headline': author.get('headline', ''),
                    'url': f"https://zhuanlan.zhihu.com/p/{obj.get('id')}" if obj.get('id') else '',
                    'crawl_time': datetime.now().isoformat(),
                })
    return items

# ============ 爬取评论 ============
def crawl_comments(item):
    """爬取单个回答/文章下的评论"""
    unique_id = item['unique_id']
    item_type = item['type']
    
    if item_type == 'answer':
        answer_id = item.get('answer_id')
        if not answer_id:
            return 0
        get_comments_fn = lambda offset: get_answer_comments(answer_id, offset)
    elif item_type == 'article':
        article_id = item.get('article_id')
        if not article_id:
            return 0
        get_comments_fn = lambda offset: get_article_comments(article_id, offset)
    else:
        return 0
    
    total_saved = 0
    for page in range(COMMENT_PAGES):
        offset = page * 20
        data = get_comments_fn(offset)
        if not data:
            break
        
        for comment in data.get('data', []):
            comment_id = comment.get('id')
            if not comment_id:
                continue
            
            author = comment.get('author', {}) or {}
            reply_to = comment.get('reply_to_author', {}) or {}
            
            comment_doc = {
                'comment_id': str(comment_id),
                'parent_unique_id': unique_id,
                'parent_type': item_type,
                'parent_answer_id': item.get('answer_id'),
                'parent_article_id': item.get('article_id'),
                'keyword': item['keyword'],
                'content': comment.get('content', '') or '',
                'vote_count': comment.get('vote_count', 0),
                'reply_count': comment.get('reply_count', 0),
                'created_time': comment.get('created_time'),
                'updated_time': comment.get('updated_time'),
                'author_name': author.get('name', ''),
                'author_url': author.get('url', ''),
                'author_headline': author.get('headline', ''),
                'reply_to_author': reply_to.get('name', ''),
                'crawl_time': datetime.now().isoformat(),
            }
            
            try:
                comments_collection.update_one(
                    {'comment_id': comment_doc['comment_id']},
                    {'$set': comment_doc},
                    upsert=True
                )
                total_saved += 1
            except Exception as e:
                pass
        
        # 检查是否还有下一页
        paging = data.get('paging', {})
        if paging.get('is_end', True):
            break
        
        time.sleep(0.5)
    
    return total_saved

# ============ 保存到 MongoDB ============
def save_to_mongodb(items):
    if not items:
        return 0
    
    saved = 0
    for item in items:
        try:
            collection.update_one(
                {'unique_id': item['unique_id']},
                {'$set': item},
                upsert=True
            )
            saved += 1
        except Exception as e:
            print(f"      保存失败 {item.get('unique_id')}: {e}")
    return saved

# ============ 导出 CSV ============
def export_to_csv():
    output_file = os.path.join(os.path.dirname(__file__), 'zhihu_search_results.csv')
    
    all_data = list(collection.find({}, {'_id': 0}).sort([('keyword', 1), ('created_time', 1)]))
    
    if not all_data:
        print("没有数据可导出")
        return
    
    fieldnames = ['keyword', 'type', 'unique_id', 'question_id', 'question_title', 
                  'answer_id', 'article_id', 'title', 'content', 'excerpt',
                  'voteup_count', 'comment_count', 'created_time', 'updated_time',
                  'author_name', 'author_url', 'author_headline', 'url', 'crawl_time']
    
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for item in all_data:
            writer.writerow(item)
    
    print(f"\n已导出 {len(all_data)} 条数据到: {output_file}")
    return output_file

def export_comments_to_csv():
    """导出评论到 CSV"""
    output_file = os.path.join(os.path.dirname(__file__), 'zhihu_comments.csv')
    
    all_data = list(comments_collection.find({}, {'_id': 0}).sort([('parent_unique_id', 1), ('created_time', 1)]))
    
    if not all_data:
        print("没有评论数据可导出")
        return
    
    fieldnames = ['comment_id', 'parent_unique_id', 'parent_type', 'keyword',
                  'content', 'vote_count', 'reply_count', 'created_time', 'updated_time',
                  'author_name', 'author_url', 'author_headline', 'reply_to_author', 'crawl_time']
    
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for item in all_data:
            writer.writerow(item)
    
    print(f"已导出 {len(all_data)} 条评论到: {output_file}")
    return output_file

# ============ 统计 ============
def print_stats():
    total = collection.count_documents({})
    total_comments = comments_collection.count_documents({})
    
    by_keyword = collection.aggregate([
        {'$group': {'_id': '$keyword', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ])
    by_type = collection.aggregate([
        {'$group': {'_id': '$type', 'count': {'$sum': 1}}}
    ])
    
    print(f"\n{'='*50}")
    print(f"MongoDB 数据统计")
    print(f"{'='*50}")
    print(f"搜索内容总计: {total} 条")
    print(f"评论总计: {total_comments} 条")
    print(f"\n按关键词:")
    for item in by_keyword:
        print(f"  {item['_id']}: {item['count']}")
    print(f"\n按类型:")
    for item in by_type:
        print(f"  {item['_id']}: {item['count']}")

# ============ 主爬取逻辑 ============
def crawl_keyword(keyword, start_offset=0):
    """爬取单个关键词"""
    print(f"\n开始爬取: {keyword}")
    total_saved = 0
    total_comments = 0
    page = start_offset // PAGE_SIZE
    
    while page < MAX_PAGES:
        offset = page * PAGE_SIZE
        print(f"  第 {page+1} 页 (offset={offset})...")
        
        data = search_zhihu(keyword, offset)
        if not data:
            print(f"  请求失败，跳过")
            break
        
        items = extract_items(data, keyword)
        if not items:
            print(f"  本页无有效结果")
        
        saved = save_to_mongodb(items)
        total_saved += saved
        print(f"  保存 {saved} 条 (累计 {total_saved})")
        
        # 爬取评论
        for item in items:
            comment_count = crawl_comments(item)
            if comment_count > 0:
                total_comments += comment_count
                print(f"    评论: {comment_count} 条 (累计 {total_comments})")
            time.sleep(0.3)
        
        # 检查是否还有下一页
        paging = data.get('paging', {})
        if paging.get('is_end', True):
            print(f"  已到最后一页")
            break
        
        page += 1
        time.sleep(REQUEST_INTERVAL)
    
    return total_saved, total_comments

def main():
    print("=" * 60)
    print("知乎搜索爬虫（含评论）")
    print("=" * 60)
    
    # 加载进度
    progress = load_progress()
    
    for keyword in KEYWORDS:
        # 检查是否已完成
        if keyword in progress and progress[keyword].get('completed'):
            print(f"\n跳过已完成: {keyword}")
            continue
        
        # 获取断点偏移
        start_offset = progress.get(keyword, {}).get('offset', 0)
        
        total, total_comments = crawl_keyword(keyword, start_offset)
        
        # 更新进度
        progress[keyword] = {
            'completed': True, 
            'total': total, 
            'comments': total_comments,
            'time': datetime.now().isoformat()
        }
        save_progress(progress)
        print(f"  => 完成 {keyword}: 共保存 {total} 条, 评论 {total_comments} 条")
    
    # 统计
    print_stats()
    
    # 导出 CSV
    csv_file = export_to_csv()
    comments_csv = export_comments_to_csv()
    
    print(f"\n{'='*60}")
    print("爬取完成！")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
