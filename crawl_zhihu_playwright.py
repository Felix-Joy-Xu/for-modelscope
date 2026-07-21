#!/usr/bin/env python3
"""知乎数据爬虫 - 使用 Playwright 浏览器自动化"""
import os, sys, time, random, hashlib, json, logging, asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, List

from playwright.async_api import async_playwright, Page, Browser
from pymongo import MongoClient, errors as mongo_errors

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/coding_labor")
DB_NAME = os.getenv("DB_NAME", "coding_labor")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("crawler_zhihu.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 中文关键词（与 GitHub 爬虫一致）
KEYWORDS = [
    'AI编程', 'Copilot', 'Cursor编辑器', 'vibe coding', '氛围编程', 'AI写代码',
    '代码审查 AI', 'AI结对编程', 'AI生成代码',
    '不需要学编程', '调prompt就行', '程序员技能贬值', 'CRUD工程师末日',
    '胶水代码', '不需要懂底层', '编程门槛降低',
    '初级程序员失业', '外包程序员 AI', '架构师 AI', '程序员两极分化',
    '中级程序员消失', '全栈工程师 AI',
    '程序员裁员', 'AI裁员', '产出增加工资不变', '老板买AI裁员', '剩余价值',
    '程序员被剥削', '效率提升归谁',
    '程序员35岁危机', '程序员转行', '考公 程序员', '程序员失业',
    '程序员焦虑', '技术人退路', '被优化', '互联网寒冬',
    'AI控制程序员', '程序员自主性', 'AI替代决策', '代码工人'
]

PHASE_A_START = datetime(2022, 11, 30, tzinfo=timezone.utc)
PHASE_A_END = datetime(2024, 2, 29, tzinfo=timezone.utc)
PHASE_B_START = datetime(2024, 3, 1, tzinfo=timezone.utc)
PHASE_B_END = datetime(2026, 5, 8, tzinfo=timezone.utc)

class DB:
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name]
        self.collection = self.db["raw_posts"]
        logger.info(f"[DB] Connected to {db_name}")

    @staticmethod
    def generate_id(doc: Dict) -> str:
        url = doc.get("url", "")
        text_prefix = doc.get("text", "")[:100]
        return hashlib.sha256(f"{url}_{text_prefix}".encode()).hexdigest()

    def insert(self, doc: Dict) -> bool:
        try:
            doc_id = self.generate_id(doc)
            doc["_id"] = doc_id
            doc["crawled_at"] = datetime.now(timezone.utc).isoformat()
            doc["version"] = "1.0"
            self.collection.insert_one(doc)
            return True
        except mongo_errors.DuplicateKeyError:
            return True
        except Exception as e:
            logger.error(f"[DB] Insert error: {e}")
            return False

    def close(self):
        self.client.close()


class ZhihuPlaywrightCrawler:
    def __init__(self, db: DB):
        self.db = db
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def init_browser(self):
        p = await async_playwright().start()
        self.browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        self.page = await context.new_page()
        # 先访问首页获取 cookie
        await self.page.goto('https://www.zhihu.com', wait_until='networkidle')
        await asyncio.sleep(3)
        logger.info("[Browser] Initialized, cookies obtained")

    async def close(self):
        if self.browser:
            await self.browser.close()

    def get_phase(self, created_time: int) -> Optional[str]:
        """根据时间戳判断 phase"""
        dt = datetime.fromtimestamp(created_time, tz=timezone.utc)
        if PHASE_A_START <= dt <= PHASE_A_END:
            return "A"
        elif PHASE_B_START <= dt <= PHASE_B_END:
            return "B"
        return None

    async def search_keyword(self, keyword: str, phase: str) -> int:
        """搜索关键词并爬取结果"""
        total = 0
        max_pages = 5  # 每个关键词最多搜5页

        logger.info(f"[ZH] Searching: kw={keyword}, phase={phase}")

        for page_num in range(max_pages):
            offset = page_num * 20
            url = f"https://www.zhihu.com/search?type=content&q={keyword}&offset={offset}"
            
            try:
                await self.page.goto(url, wait_until='networkidle', timeout=30000)
                await asyncio.sleep(random.uniform(3, 5))
                
                # 等待搜索结果加载
                await self.page.wait_for_selector('.SearchResult-card, .Card', timeout=10000)
                
                # 提取搜索结果
                results = await self.page.evaluate('''() => {
                    const items = [];
                    // 尝试多种选择器
                    const cards = document.querySelectorAll('.SearchResult-card, .Card[data-za-module="SearchResult"], .List-item');
                    cards.forEach(card => {
                        const link = card.querySelector('a[href*="/question/"]');
                        if (!link) return;
                        
                        const href = link.getAttribute('href') || '';
                        const title = link.textContent?.trim() || '';
                        
                        // 提取问题ID
                        const match = href.match(/\/question\/(\d+)/);
                        const questionId = match ? match[1] : '';
                        
                        // 提取回答数
                        const meta = card.textContent || '';
                        const answerMatch = meta.match(/(\\d+)\\s*个回答/);
                        const answerCount = answerMatch ? parseInt(answerMatch[1]) : 0;
                        
                        items.push({
                            questionId,
                            title,
                            url: href.startsWith('http') ? href : 'https://www.zhihu.com' + href,
                            answerCount,
                        });
                    });
                    return items;
                }''')
                
                if not results:
                    logger.info(f"  No results on page {page_num+1}")
                    break
                
                logger.info(f"  Page {page_num+1}: {len(results)} results")
                
                for result in results:
                    if not result.get('questionId'):
                        continue
                    
                    # 获取问题详情页
                    await self._crawl_question(result['questionId'], result['title'],
                                               result['url'], keyword, phase)
                    total += 1
                    await asyncio.sleep(random.uniform(2, 4))
                
                await asyncio.sleep(random.uniform(3, 6))
                
            except Exception as e:
                logger.error(f"  Error searching '{keyword}' page {page_num+1}: {e}")
                await asyncio.sleep(5)
                continue

        logger.info(f"[ZH] Finished: {total} items for '{keyword}' phase={phase}")
        return total

    async def _crawl_question(self, question_id: str, title: str, url: str,
                               keyword: str, phase: str):
        """爬取单个问题页面"""
        try:
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # 提取问题信息
            question_data = await self.page.evaluate('''() => {
                const data = {};
                
                // 问题详情
                const detail = document.querySelector('.QuestionHeader-detail, .RichText');
                data.detail = detail ? detail.textContent?.trim() || '' : '';
                
                // 关注数
                const follower = document.querySelector('.NumberBoard-item:first-child .NumberBoard-itemValue');
                data.followerCount = follower ? follower.textContent?.trim() || '0' : '0';
                
                // 浏览数
                const viewer = document.querySelector('.NumberBoard-item:last-child .NumberBoard-itemValue');
                data.viewerCount = viewer ? viewer.textContent?.trim() || '0' : '0';
                
                // 回答列表
                const answers = [];
                const answerCards = document.querySelectorAll('.AnswerCard, .List-item');
                answerCards.forEach(card => {
                    const content = card.querySelector('.RichText');
                    const author = card.querySelector('.AuthorInfo-name, .UserLink-link');
                    const vote = card.querySelector('.VoteButton--up, .VoterButton');
                    const time = card.querySelector('.ContentItem-time, .PublishTime');
                    
                    answers.push({
                        content: content ? content.textContent?.trim() || '' : '',
                        author: author ? author.textContent?.trim() || '' : '',
                        votes: vote ? vote.textContent?.trim() || '0' : '0',
                        time: time ? time.textContent?.trim() || '' : '',
                    });
                });
                
                data.answers = answers;
                return data;
            }''')
            
            # 存储问题
            q_doc = {
                "source": "zhihu_question",
                "phase": phase,
                "lang": "zh",
                "url": url,
                "title": title,
                "text": question_data.get('detail', ''),
                "created_at": "",
                "author": "",
                "metadata": {
                    "question_id": question_id,
                    "search_keyword": keyword,
                    "follower_count": question_data.get('followerCount', '0'),
                    "viewer_count": question_data.get('viewerCount', '0'),
                }
            }
            self.db.insert(q_doc)
            
            # 存储回答
            for ans in question_data.get('answers', []):
                if not ans.get('content'):
                    continue
                    
                ans_doc = {
                    "source": "zhihu_answer",
                    "phase": phase,
                    "lang": "zh",
                    "url": url,
                    "title": "",
                    "text": ans['content'],
                    "created_at": ans.get('time', ''),
                    "author": ans.get('author', ''),
                    "metadata": {
                        "question_id": question_id,
                        "question_title": title,
                        "search_keyword": keyword,
                        "vote_count": ans.get('votes', '0'),
                    }
                }
                self.db.insert(ans_doc)
                
        except Exception as e:
            logger.error(f"  Error crawling question {question_id}: {e}")


async def main():
    logger.info("=" * 60)
    logger.info("知乎数据爬虫 (Playwright)")
    logger.info("=" * 60)

    db = DB(MONGO_URI, DB_NAME)
    crawler = ZhihuPlaywrightCrawler(db)
    
    try:
        await crawler.init_browser()
        
        # Phase A
        total_a = 0
        logger.info(f">>> Phase A: 2022-11-30 ~ 2024-02-29")
        for kw in KEYWORDS:
            logger.info(f"[Crawl] '{kw}' Phase A...")
            count = await crawler.search_keyword(kw, "A")
            total_a += count
            await asyncio.sleep(random.uniform(3, 6))
        
        # Phase B
        total_b = 0
        logger.info(f">>> Phase B: 2024-03-01 ~ 2026-05-08")
        for kw in KEYWORDS:
            logger.info(f"[Crawl] '{kw}' Phase B...")
            count = await crawler.search_keyword(kw, "B")
            total_b += count
            await asyncio.sleep(random.uniform(3, 6))
        
        logger.info("=" * 60)
        logger.info(f"知乎 crawl complete: A={total_a}, B={total_b}, total={total_a+total_b}")
        logger.info("=" * 60)
        
    finally:
        await crawler.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
