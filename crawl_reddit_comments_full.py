import os as _os
try:
    from _secrets import REDDIT_COOKIES
except ImportError:
    REDDIT_COOKIES = _os.environ.get("REDDIT_COOKIES", "")

"""
Reddit 全量评论抓取脚本
读取已有帖子列表，为每个有评论的帖子抓取全部评论（含子回复）
带断点续爬功能
"""

import requests
import csv
import json
import os
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_FILE = os.path.join(BASE_DIR, "reddit_posts.csv")
COMMENTS_FILE = os.path.join(BASE_DIR, "reddit_comments.csv")
STATE_FILE = os.path.join(BASE_DIR, "crawl_comments_state.json")

# Reddit cookies - 从浏览器复制


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Cookie': REDDIT_COOKIES
}

def ts_to_str(ts):
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return ''

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

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'completed_posts': []}

def extract_comments(keyword, post_id, data, parent_permalink='', depth=0, max_depth=5):
    """递归提取评论（含子回复）"""
    comments = []
    if depth > max_depth:
        return comments

    children = data.get('data', {}).get('children', []) if 'data' in data else data

    for child in children:
        if not isinstance(child, dict):
            continue

        kind = child.get('kind', '')
        d = child.get('data', {})

        if kind == 't1':  # 普通评论
            text = d.get('body', '') or ''
            if len(text) > 5000:
                text = text[:5000] + '...'

            permalink = d.get('permalink', '')
            if permalink and not permalink.startswith('http'):
                permalink = f"https://www.reddit.com{permalink}"

            comments.append({
                'keyword': keyword,
                'post_id': post_id,
                'comment_id': d.get('id', ''),
                'author': d.get('author', '[deleted]'),
                'text': text,
                'score': d.get('score', 0),
                'created_utc': ts_to_str(d.get('created_utc', 0)),
                'permalink': permalink
            })

            # 递归抓取子回复
            replies = d.get('replies', {})
            if replies and isinstance(replies, dict):
                sub_comments = extract_comments(
                    keyword, post_id, replies,
                    parent_permalink=permalink,
                    depth=depth + 1,
                    max_depth=max_depth
                )
                comments.extend(sub_comments)

        elif kind == 'more':  # "查看更多" 占位符
            # 尝试通过 morechildren API 获取更多评论
            children_ids = d.get('children', [])
            if children_ids and len(children_ids) <= 50:
                more_comments = fetch_more_children(keyword, post_id, children_ids)
                comments.extend(more_comments)

    return comments

def fetch_more_children(keyword, post_id, children_ids):
    """通过 morechildren API 获取折叠的评论"""
    comments = []
    ids_str = ','.join(children_ids[:50])  # 一次最多 50 个
    url = f'https://www.reddit.com/r/all/comments/{post_id}/_/api/morechildren.json?link_id=t3_{post_id}&children={ids_str}&limit_children=true'

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            things = data.get('json', {}).get('data', {}).get('things', [])
            for thing in things:
                if thing.get('kind') == 't1':
                    d = thing.get('data', {})
                    text = d.get('body', '') or ''
                    if len(text) > 5000:
                        text = text[:5000] + '...'
                    permalink = d.get('permalink', '')
                    if permalink and not permalink.startswith('http'):
                        permalink = f"https://www.reddit.com{permalink}"
                    comments.append({
                        'keyword': keyword,
                        'post_id': post_id,
                        'comment_id': d.get('id', ''),
                        'author': d.get('author', '[deleted]'),
                        'text': text,
                        'score': d.get('score', 0),
                        'created_utc': ts_to_str(d.get('created_utc', 0)),
                        'permalink': permalink
                    })
    except:
        pass

    return comments

def get_all_comments(keyword, post_id, permalink, max_comments=200):
    """获取帖子的所有评论（含子回复）"""
    url = f'https://www.reddit.com{permalink}.json?limit={max_comments}&raw_json=1'

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return []

        data = resp.json()
        if len(data) < 2:
            return []

        # 递归提取所有评论
        comments = extract_comments(keyword, post_id, data[1])
        return comments

    except Exception as e:
        return []

def main():
    print("=" * 60)
    print("Reddit 全量评论抓取")
    print("=" * 60)

    # 读取所有帖子
    if not os.path.exists(POSTS_FILE):
        print(f"错误: {POSTS_FILE} 不存在，请先运行 crawl_reddit.py")
        return

    posts = []
    with open(POSTS_FILE, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            posts.append(row)

    print(f"帖子总数: {len(posts)}")

    # 过滤有评论的帖子
    posts_with_comments = [p for p in posts if int(p.get('num_comments', 0)) > 0]
    print(f"有评论的帖子: {len(posts_with_comments)}")

    # 加载断点状态
    state = load_state()
    completed = set(state.get('completed_posts', []))
    remaining = [p for p in posts_with_comments if p['id'] not in completed]

    print(f"已抓取评论的帖子: {len(completed)}")
    print(f"待抓取: {len(remaining)}")
    print()

    if not remaining:
        print("所有帖子的评论已抓取完成!")
        return

    total_new_comments = 0
    start_time = time.time()

    for i, post in enumerate(remaining):
        post_id = post['id']
        keyword = post['keyword']
        permalink = post.get('permalink', '')
        num_comments = int(post.get('num_comments', 0))

        if not permalink:
            completed.add(post_id)
            continue

        print(f"[{i+1}/{len(remaining)}] r/{post.get('subreddit','?')} | {post.get('title','')[:50]}... | {num_comments} 条评论")

        comments = get_all_comments(keyword, post_id, permalink, max_comments=200)

        if comments:
            save_comments(comments)
            total_new_comments += len(comments)
            print(f"  → 抓取 {len(comments)} 条评论 (累计: {total_new_comments})")

        completed.add(post_id)
        save_state({'completed_posts': list(completed)})

        # 限速
        time.sleep(1.5)

        # 每 100 个帖子显示进度
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed * 60
            print(f"\n  📊 进度: {i+1}/{len(remaining)}, 评论: {total_new_comments}, 速度: {speed:.0f} 帖/分钟\n")

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"✅ 全量评论抓取完成!")
    print(f"   处理帖子: {len(completed)} 个")
    print(f"   新增评论: {total_new_comments} 条")
    print(f"   耗时: {elapsed/60:.1f} 分钟")
    print(f"{'=' * 60}")

if __name__ == '__main__':
    main()
