"""
Reddit 数据爬虫 - 使用 Reddit JSON API
抓取 20 个 AI 关键词的帖子和评论
"""

import requests
import csv
import json
import os
import time
from datetime import datetime, timezone

KEYWORDS = [
    "AI", "Artificial Intelligence", "Machine Learning", "Deep Learning",
    "LLM", "Large Language Model", "ChatGPT", "GPT-4", "Transformer",
    "Neural Network", "Computer Vision", "NLP", "Reinforcement Learning",
    "Generative AI", "AI Agent", "RAG", "Fine-tuning", "Prompt Engineering",
    "Diffusion Model", "AI Safety"
]

OUTPUT_FILE = "reddit_posts.csv"
COMMENTS_FILE = "reddit_comments.csv"
STATE_FILE = "crawl_reddit_state.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def save_posts(posts):
    file_exists = os.path.exists(OUTPUT_FILE)
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'keyword', 'id', 'title', 'text', 'author', 'subreddit',
            'score', 'upvote_ratio', 'num_comments', 'created_utc',
            'url', 'permalink'
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerows(posts)
    print(f"  已保存 {len(posts)} 条帖子到 {OUTPUT_FILE}")

def save_comments(comments):
    if not comments:
        return
    file_exists = os.path.exists(COMMENTS_FILE)
    with open(COMMENTS_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'keyword', 'post_id', 'comment_id', 'author', 'text',
            'score', 'created_utc', 'permalink'
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerows(comments)
    print(f"  已保存 {len(comments)} 条评论到 {COMMENTS_FILE}")

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'completed_keywords': []}

def ts_to_str(ts):
    """时间戳转字符串"""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return ''

def search_reddit(keyword, limit=100):
    """搜索 Reddit 帖子"""
    posts = []

    for sort in ['relevance', 'new']:
        url = f'https://www.reddit.com/r/all/search.json?q={keyword}&limit={limit}&sort={sort}&t=all'

        max_retries = 5
        resp = None
        for retry in range(max_retries):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 429:
                    wait = 30 * (retry + 1)
                    print(f"    {sort}: 429 限流, 等待 {wait} 秒后重试 ({retry+1}/{max_retries})...")
                    time.sleep(wait)
                    continue
                elif resp.status_code != 200:
                    print(f"    {sort}: HTTP {resp.status_code}")
                    resp = None
                    break
                break
            except Exception as e:
                if retry < max_retries - 1:
                    print(f"    {sort}: 失败 {str(e)[:40]}, 重试 ({retry+1}/{max_retries})...")
                    time.sleep(10)
                    continue
                print(f"    {sort}: 失败 {str(e)[:40]}")
                resp = None
                break

        if resp is None:
            continue

        try:
            data = resp.json()
            children = data.get('data', {}).get('children', [])

            for child in children:
                d = child['data']
                if d.get('stickied') or not d.get('title'):
                    continue

                text = d.get('selftext', '') or ''
                if len(text) > 5000:
                    text = text[:5000] + '...'

                posts.append({
                    'keyword': keyword,
                    'id': d.get('id', ''),
                    'title': d.get('title', ''),
                    'text': text,
                    'author': d.get('author', '[deleted]'),
                    'subreddit': d.get('subreddit', ''),
                    'score': d.get('score', 0),
                    'upvote_ratio': d.get('upvote_ratio', 0),
                    'num_comments': d.get('num_comments', 0),
                    'created_utc': ts_to_str(d.get('created_utc', 0)),
                    'url': f"https://www.reddit.com{d.get('permalink', '')}",
                    'permalink': d.get('permalink', '')
                })

            print(f"    {sort}: {len(children)} 条")
            time.sleep(2)
        except Exception as e:
            print(f"    {sort} 解析失败: {str(e)[:60]}")

    # 去重
    seen = set()
    unique_posts = []
    for p in posts:
        if p['id'] not in seen:
            seen.add(p['id'])
            unique_posts.append(p)

    return unique_posts

def get_comments(keyword, post_id, permalink, max_comments=50):
    """获取帖子的评论"""
    comments = []
    url = f'https://www.reddit.com{permalink}.json?limit={max_comments}'

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return comments

        data = resp.json()
        if len(data) < 2:
            return comments

        comment_list = data[1].get('data', {}).get('children', [])

        for child in comment_list:
            if child['kind'] != 't1':
                continue

            d = child['data']
            text = d.get('body', '') or ''
            if len(text) > 2000:
                text = text[:2000] + '...'

            comments.append({
                'keyword': keyword,
                'post_id': post_id,
                'comment_id': d.get('id', ''),
                'author': d.get('author', '[deleted]'),
                'text': text,
                'score': d.get('score', 0),
                'created_utc': ts_to_str(d.get('created_utc', 0)),
                'permalink': f"https://www.reddit.com{d.get('permalink', '')}"
            })

            if len(comments) >= max_comments:
                break

    except Exception as e:
        pass

    return comments

def main():
    print("=" * 60)
    print("Reddit 数据爬虫")
    print(f"关键词: {len(KEYWORDS)} 个")
    print("=" * 60)

    state = load_state()
    completed = set(state.get('completed_keywords', []))
    remaining = [kw for kw in KEYWORDS if kw not in completed]

    if not remaining:
        print("所有关键词已爬取完成!")
        return

    print(f"待爬取: {len(remaining)}/{len(KEYWORDS)}")
    print(f"已爬取: {len(completed)}")
    print()

    for i, kw in enumerate(remaining):
        print(f"[{i+1}/{len(remaining)}] {kw}")

        posts = search_reddit(kw, limit=100)
        if posts:
            save_posts(posts)

            total_comments = 0
            for j, post in enumerate(posts):
                if post['num_comments'] > 0 and j < 20:
                    comments = get_comments(kw, post['id'], post['permalink'], max_comments=30)
                    if comments:
                        save_comments(comments)
                        total_comments += len(comments)
                    time.sleep(1)

            print(f"  ★ {kw}: {len(posts)} 条帖子, {total_comments} 条评论")
        else:
            print(f"  ★ {kw}: 0 条")

        completed.add(kw)
        save_state({'completed_keywords': list(completed)})
        print()

    print("=" * 60)
    print("爬取完成!")

if __name__ == '__main__':
    main()
