import sqlite3
import json
import time
import re
from datetime import datetime
import sys

DB_PATH = r'D:\国际比较政治经济学\文献\ai_research.db'
INPUT_FILE = r'D:\国际比较政治经济学\国际比较政治经济学\ai\massive_pr_crawl_results.jsonl'
CHUNK_SIZE = 50000

KEYWORDS = ["copilot", "cursor", "chatgpt", "sweep", "mentally draining", "ai code", "ai generated"]

def infer_keyword(text):
    text_lower = text.lower()
    for kw in KEYWORDS:
        if kw in text_lower:
            return kw
    return "ai_programming"

def main():
    print("="*60)
    print(" MASSIVE GITHUB DATASET INTEGRATION")
    print("="*60)
    
    # 1. Connect to SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        return

    # Ensure tables exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            keyword TEXT,
            title TEXT,
            content TEXT,
            score INTEGER,
            comments_count INTEGER,
            created_at TEXT,
            language TEXT,
            category TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            keyword TEXT,
            content TEXT,
            score INTEGER,
            created_at TEXT,
            category TEXT
        )
    """)
    conn.commit()

    posts_buffer = []
    comments_buffer = []
    
    total_processed = 0
    total_posts = 0
    total_comments = 0
    start_time = time.time()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Started reading JSONL...")

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                data = json.loads(line)
            except:
                continue

            total_processed += 1
            
            p_type = data.get('type', 'pull_request')
            text = data.get('text', '')
            created_at = data.get('created_at', '')
            url = data.get('url', '')
            
            year = created_at[:4] if created_at else ""
            if year not in ('2026',):
                continue
            
            kw = infer_keyword(text)

            if p_type == 'pull_request':
                # title = URL fallback
                posts_buffer.append((
                    'github', kw, url, text, 0, 0, created_at, 'en/zh mixed', 'pull_request'
                ))
                total_posts += 1
            else:
                comments_buffer.append((
                    'github', kw, text, 0, created_at, p_type
                ))
                total_comments += 1

            # Flush buffers in chunks
            if len(posts_buffer) >= CHUNK_SIZE:
                cursor.executemany("""
                    INSERT INTO posts (platform, keyword, title, content, score, comments_count, created_at, language, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, posts_buffer)
                conn.commit()
                posts_buffer.clear()
                
            if len(comments_buffer) >= CHUNK_SIZE:
                cursor.executemany("""
                    INSERT INTO comments (platform, keyword, content, score, created_at, category)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, comments_buffer)
                conn.commit()
                comments_buffer.clear()

            # Log progress
            if total_processed % 100000 == 0:
                elapsed = time.time() - start_time
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Processed {total_processed:,} records... (Elapsed: {elapsed:.1f}s)")

    # Final flush
    if posts_buffer:
        cursor.executemany("""
            INSERT INTO posts (platform, keyword, title, content, score, comments_count, created_at, language, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, posts_buffer)
        conn.commit()
    
    if comments_buffer:
        cursor.executemany("""
            INSERT INTO comments (platform, keyword, content, score, created_at, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, comments_buffer)
        conn.commit()

    conn.close()
    
    elapsed = time.time() - start_time
    print("="*60)
    print(f" INTEGRATION COMPLETE!")
    print(f" Total Processed: {total_processed:,}")
    print(f" Inserted Posts : {total_posts:,}")
    print(f" Inserted Comms : {total_comments:,}")
    print(f" Total Time     : {elapsed:.1f}s")
    print("="*60)

if __name__ == "__main__":
    # Ensure flush for background task logging
    sys.stdout.reconfigure(line_buffering=True)
    main()
