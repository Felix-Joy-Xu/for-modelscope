"""
Twitter/X 数据爬虫 - 启动 Edge CDP + Playwright 连接
同时抓取 Top（热门）和 Latest（最新）两种视图，大幅增加数据量
"""

import asyncio
import csv
import json
import os
import time
import subprocess
import urllib.request
from playwright.async_api import async_playwright

# 只爬取英文关键词
KEYWORDS = [
    "AI", "Artificial Intelligence", "Machine Learning", "Deep Learning",
    "LLM", "Large Language Model", "ChatGPT", "GPT-4", "Transformer",
    "Neural Network", "Computer Vision", "NLP", "Reinforcement Learning",
    "Generative AI", "AI Agent", "RAG", "Fine-tuning", "Prompt Engineering",
    "Diffusion Model", "AI Safety"
]

OUTPUT_FILE = "twitter_tweets.csv"
STATE_FILE = "crawl_twitter_state.json"

def save_tweets(tweets):
    file_exists = os.path.exists(OUTPUT_FILE)
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'keyword', 'source', 'user', 'text', 'time', 'replies', 'retweets', 'likes', 'url'
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerows(tweets)
    print(f"  已保存 {len(tweets)} 条到 {OUTPUT_FILE}")

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'completed_keywords': []}

async def extract_tweet(article, keyword, source):
    """从 article 元素提取推文数据"""
    try:
        text_el = await article.query_selector('[data-testid="tweetText"]')
        if not text_el:
            return None
        text = await text_el.inner_text()
        if not text.strip():
            return None
        
        # 用户名
        name_el = await article.query_selector('[data-testid="User-Name"]')
        name = await name_el.inner_text() if name_el else ""
        
        # 时间
        time_el = await article.query_selector('time')
        time_str = await time_el.get_attribute('datetime') if time_el else ""
        
        # 链接
        link_el = await article.query_selector('a[href*="/status/"]')
        url = ""
        if link_el:
            url = await link_el.get_attribute('href') or ""
            if url and not url.startswith('http'):
                url = f"https://x.com{url}"
        
        # 互动数据
        replies = retweets = likes = ""
        try:
            reply_el = await article.query_selector('[data-testid="reply"]')
            if reply_el:
                reply_text = await reply_el.inner_text()
                replies = reply_text.strip()
        except:
            pass
        try:
            retweet_el = await article.query_selector('[data-testid="retweet"]')
            if retweet_el:
                retweet_text = await retweet_el.inner_text()
                retweets = retweet_text.strip()
        except:
            pass
        try:
            like_el = await article.query_selector('[data-testid="like"]')
            if like_el:
                like_text = await like_el.inner_text()
                likes = like_text.strip()
        except:
            pass
        
        return {
            'keyword': keyword,
            'source': source,
            'user': name.strip(),
            'text': text.strip(),
            'time': time_str,
            'replies': replies,
            'retweets': retweets,
            'likes': likes,
            'url': url
        }
    except:
        return None

async def scroll_and_collect(page, keyword, source, max_tweets=200):
    """滚动页面并收集推文"""
    tweets = []
    seen_urls = set()
    
    # 等待推文加载
    try:
        await page.wait_for_selector('article', timeout=15000)
    except:
        print(f"    {keyword} ({source}): 无推文结果")
        return tweets
    
    await asyncio.sleep(2)
    
    for scroll_round in range(50):  # 最多滚动 50 次
        articles = await page.query_selector_all('article')
        
        new_count = 0
        for article in articles:
            tweet = await extract_tweet(article, keyword, source)
            if tweet and tweet['url'] not in seen_urls:
                seen_urls.add(tweet['url'])
                tweets.append(tweet)
                new_count += 1
        
        if new_count > 0:
            print(f"    {source}: 已获取 {len(tweets)} 条...")
        
        if len(tweets) >= max_tweets:
            break
        
        # 滚动
        await page.evaluate('window.scrollBy(0, 1200)')
        await asyncio.sleep(1.5)
        
        # 每 10 轮检查一次是否没有新内容
        if scroll_round > 0 and scroll_round % 10 == 0:
            old_count = len(tweets)
            await asyncio.sleep(3)  # 多等一会儿
            articles = await page.query_selector_all('article')
            for article in articles:
                tweet = await extract_tweet(article, keyword, source)
                if tweet and tweet['url'] not in seen_urls:
                    seen_urls.add(tweet['url'])
                    tweets.append(tweet)
            if len(tweets) == old_count:
                print(f"    {source}: 没有更多推文了")
                break
    
    return tweets

async def search_keyword(page, keyword, max_tweets=200):
    """搜索单个关键词 - 同时抓取 Top 和 Latest"""
    all_tweets = []
    seen_urls = set()
    
    # ====== 1. 先抓 Top（热门） ======
    top_url = f"https://x.com/search?q={keyword}&src=typed_query"
    print(f"  搜索 Top: {keyword}")
    
    try:
        await page.goto(top_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # 确保在 Top 标签
        try:
            top_link = await page.query_selector('a[href*="f=top"]')
            if top_link:
                await top_link.click()
                await asyncio.sleep(2)
        except:
            pass
        
        top_tweets = await scroll_and_collect(page, keyword, "Top", max_tweets // 2)
        for t in top_tweets:
            if t['url'] not in seen_urls:
                seen_urls.add(t['url'])
                all_tweets.append(t)
        print(f"  ✓ Top: {len(top_tweets)} 条")
    except Exception as e:
        print(f"  ⚠ Top 失败: {str(e)[:60]}")
    
    # ====== 2. 再抓 Latest（最新） ======
    latest_url = f"https://x.com/search?q={keyword}&src=typed_query&f=live"
    print(f"  搜索 Latest: {keyword}")
    
    try:
        await page.goto(latest_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # 确保在 Latest 标签
        try:
            latest_link = await page.query_selector('a[href*="f=live"]')
            if latest_link:
                await latest_link.click()
                await asyncio.sleep(2)
        except:
            pass
        
        latest_tweets = await scroll_and_collect(page, keyword, "Latest", max_tweets // 2)
        for t in latest_tweets:
            if t['url'] not in seen_urls:
                seen_urls.add(t['url'])
                all_tweets.append(t)
        print(f"  ✓ Latest: {len(latest_tweets)} 条")
    except Exception as e:
        print(f"  ⚠ Latest 失败: {str(e)[:60]}")
    
    print(f"  ★ {keyword}: 共 {len(all_tweets)} 条 (去重后)")
    return all_tweets

async def main():
    print("=" * 60)
    print("Twitter/X 数据爬虫 v2 (Edge CDP)")
    print("同时抓取 Top + Latest，大幅增加数据量")
    print("关键词总数: 20")
    print("=" * 60)
    
    state = load_state()
    completed = set(state.get('completed_keywords', []))
    remaining = [kw for kw in KEYWORDS if kw not in completed]
    
    if not remaining:
        print("所有关键词已爬取完成!")
        return
    
    print(f"待爬取: {len(remaining)}/20")
    print(f"已爬取: {len(completed)}")
    print()
    
    # 启动 Edge（带 CDP 端口）
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    user_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Edge', 'User Data')
    
    cmd = [
        edge_path,
        f'--user-data-dir={user_data_dir}',
        '--remote-debugging-port=9222',
        '--no-first-run',
        '--no-default-browser-check'
    ]
    
    print("正在启动 Edge（带远程调试端口）...")
    subprocess.Popen(cmd)
    
    # 等待 Edge 启动并开放 CDP 端口
    for i in range(30):
        try:
            resp = urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
            data = json.loads(resp.read())
            print(f"✓ Edge CDP 已就绪 ({data.get('Browser', '?')})")
            break
        except:
            if i < 29:
                print(f"  等待 Edge 启动... ({i+1}/30)")
                await asyncio.sleep(2)
            else:
                print("✗ Edge 启动超时")
                return
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        print("✓ 已连接到 Edge")
        
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        
        # 检查登录状态
        await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)
        
        if 'login' in page.url:
            print("✗ 未登录 Twitter!")
            print("请在打开的 Edge 中登录 X（用谷歌账号）")
            print("登录完成后，按 Enter 键继续...")
            input()
            
            await page.goto('https://x.com/home', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)
        
        if 'login' in page.url:
            print("✗ 仍未登录，退出")
            return
        
        print("✓ Twitter 已登录，开始爬取...")
        print()
        
        # 逐个搜索
        for i, kw in enumerate(remaining):
            print(f"[{i+1}/{len(remaining)}] {kw}")
            tweets = await search_keyword(page, kw, 200)
            if tweets:
                save_tweets(tweets)
            completed.add(kw)
            save_state({'completed_keywords': list(completed)})
            print()
        
        print("=" * 60)
        print(f"爬取完成! 共处理 {len(completed)} 个关键词")

if __name__ == '__main__':
    asyncio.run(main())
