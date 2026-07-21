"""
CSDN 博客爬虫 - 搜索 AI 相关关键词
使用 CSDN 公开搜索 API: https://so.csdn.net/api/v2/search
"""
import requests
import csv
import time
import os
import json
from datetime import datetime

# ===== 配置 =====
KEYWORDS = [
    "大语言模型", "AI编程", "自然语言处理", "机器学习", "AI",
    "深度学习", "ChatGPT", "AI音乐", "Prompt Engineering", "AI安全",
    "RAG", "扩散模型", "AI伦理", "AI写作", "Fine-tuning",
    "强化学习", "AI视频", "大模型", "AI绘画", "计算机视觉",
    "AI Agent", "AI就业", "Transformer", "神经网络", "人工智能"
]

MAX_PAGES = 50  # 每个关键词最多爬取页数（每页约30条）
DELAY = 1.0     # 请求间隔（秒）
OUTPUT_FILE = "csdn_articles.csv"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://so.csdn.net/'
}

# ===== 状态文件（断点续爬）=====
STATE_FILE = "crawl_csdn_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed_keywords": [], "current_keyword": None, "current_page": 0}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def crawl_keyword(keyword, start_page=1):
    """爬取单个关键词"""
    articles = []
    total_results = 0
    
    for page in range(start_page, MAX_PAGES + 1):
        url = f'https://so.csdn.net/api/v2/search?q={keyword}&t=blog&p={page}'
        
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  HTTP {resp.status_code}, 停止")
                break
            
            data = resp.json()
            items = data.get('result_vos', [])
            total_results = data.get('total', 0)
            
            if not items:
                print(f"  第{page}页无数据, 停止")
                break
            
            for item in items:
                article = {
                    'keyword': keyword,
                    'article_id': item.get('articleid', ''),
                    'title': item.get('title', '').replace('<em>', '').replace('</em>', ''),
                    'url': item.get('url', '').split('?')[0],  # 去掉追踪参数
                    'description': item.get('description', '').replace('<em>', '').replace('</em>', ''),
                    'author': item.get('author', ''),
                    'nickname': item.get('nickname', ''),
                    'author_space': item.get('author_space', ''),
                    'created_at': item.get('created_at', ''),
                    'digg': item.get('digg', 0),        # 点赞
                    'view': item.get('view', 0),         # 浏览
                    'collections': item.get('collections', 0),  # 收藏
                    'comment': item.get('comment', 0),   # 评论
                    'tags': '|'.join(item.get('search_tag', [])),
                    'language': item.get('language', ''),
                    'score': item.get('score', 0),
                    'type': item.get('type', ''),
                }
                articles.append(article)
            
            print(f"  第{page}页: {len(items)} 条 (累计 {len(articles)})")
            
            # 保存当前进度
            save_state({
                "completed_keywords": [],
                "current_keyword": keyword,
                "current_page": page + 1
            })
            
            # 检查是否最后一页
            total_page = data.get('total_page', 0)
            if total_page and page >= total_page:
                print(f"  已到最后一页 (共{total_page}页)")
                break
            
            time.sleep(DELAY)
            
        except Exception as e:
            print(f"  第{page}页错误: {e}")
            time.sleep(DELAY * 3)
            continue
    
    return articles, total_results

def save_to_csv(all_articles):
    """保存到 CSV"""
    if not all_articles:
        print("没有数据可保存")
        return
    
    fieldnames = [
        'keyword', 'article_id', 'title', 'url', 'description',
        'author', 'nickname', 'author_space', 'created_at',
        'digg', 'view', 'collections', 'comment',
        'tags', 'language', 'score', 'type'
    ]
    
    file_exists = os.path.exists(OUTPUT_FILE)
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(all_articles)
    
    print(f"\n已追加 {len(all_articles)} 条到 {OUTPUT_FILE}")

def main():
    state = load_state()
    completed = set(state.get("completed_keywords", []))
    start_keyword = state.get("current_keyword")
    start_page = state.get("current_page", 1)
    
    print(f"CSDN 爬虫启动 - {datetime.now()}")
    print(f"关键词列表: {KEYWORDS}")
    print(f"已完成: {completed}")
    print(f"断点: keyword={start_keyword}, page={start_page}")
    print()
    
    total_all = 0
    keyword_started = False
    
    for keyword in KEYWORDS:
        if keyword in completed:
            print(f"[跳过] {keyword} - 已完成")
            continue
        
        # 如果设置了断点关键词，跳过之前的
        if start_keyword and not keyword_started:
            if keyword != start_keyword:
                continue
            keyword_started = True
        
        print(f"\n{'='*60}")
        print(f"[开始] 爬取关键词: {keyword}")
        print(f"{'='*60}")
        
        articles, total = crawl_keyword(keyword, start_page if keyword == start_keyword else 1)
        
        if articles:
            save_to_csv(articles)
            total_all += len(articles)
        
        print(f"[完成] {keyword}: 爬取 {len(articles)} 条 (搜索总数: {total})")
        
        # 标记完成
        completed.add(keyword)
        save_state({
            "completed_keywords": list(completed),
            "current_keyword": None,
            "current_page": 0
        })
        
        # 重置分页（下一个关键词从第1页开始）
        start_page = 1
        
        # 关键词之间间隔
        if keyword != KEYWORDS[-1]:
            time.sleep(DELAY * 2)
    
    print(f"\n{'='*60}")
    print(f"全部完成! 共爬取 {total_all} 条数据")
    print(f"输出文件: {OUTPUT_FILE}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
