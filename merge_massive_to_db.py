"""将 massive_pr_crawl_results.jsonl 追加合并到 github_prs.db（不删除已有数据）"""
import sqlite3
import json
import os

INPUT_FILE = r'D:\国际比较政治经济学\国际比较政治经济学\ai\massive_pr_crawl_results.jsonl'
DB_FILE = r'D:\国际比较政治经济学\国际比较政治经济学\ai\github_prs.db'
BATCH_SIZE = 100000

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"错误：输入文件不存在: {INPUT_FILE}")
        return
    
    # 统计总行数
    print(f"统计 {INPUT_FILE} 总行数...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        total_lines = sum(1 for _ in f)
    print(f"  总行数: {total_lines}")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 确保表存在
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pr_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            url TEXT,
            author TEXT,
            text TEXT,
            created_at TEXT,
            year_month TEXT
        )
    ''')
    
    # 查询已有记录数
    cursor.execute('SELECT COUNT(*) FROM pr_data')
    existing_count = cursor.fetchone()[0]
    print(f"  数据库已有记录: {existing_count}")
    
    # 获取已插入的URL集合用于去重（只查近期记录以节省内存）
    # 对于800万行的大表，我们使用 INSERT OR IGNORE 配合唯一索引来去重
    # 先建一个唯一索引（如果不存在）
    print("  创建去重索引（url + type + created_at）...")
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_url_type_time ON pr_data(url, type, created_at)')
    except sqlite3.OperationalError:
        print("  索引已存在或无法创建，继续...")
    
    print(f"  开始导入（从已有 {existing_count} 条之后追加）...")
    batch = []
    total_inserted = 0
    total_skipped = 0
    
    insert_sql = "INSERT OR IGNORE INTO pr_data (type, url, author, text, created_at, year_month) VALUES (?, ?, ?, ?, ?, ?)"
    
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line)
                r_type = data.get('type', '')
                url = data.get('url', '')
                author = data.get('author', '')
                text = data.get('text', '')
                created_at = data.get('created_at', '')
                year_month = created_at[:7] if created_at else ''
                
                batch.append((r_type, url, author, text, created_at, year_month))
                
                if len(batch) >= BATCH_SIZE:
                    cursor.executemany(insert_sql, batch)
                    inserted = cursor.rowcount  # 这返回的是"匹配"的行数（在IGNORE下不准确）
                    conn.commit()
                    total_inserted += len(batch)
                    if line_num % (BATCH_SIZE * 5) == 0 or line_num == total_lines:
                        pct = line_num / total_lines * 100
                        # 重新查询总数
                        cursor.execute('SELECT COUNT(*) FROM pr_data')
                        current_count = cursor.fetchone()[0]
                        print(f"  进度: {line_num}/{total_lines} ({pct:.1f}%) - DB记录: {current_count}")
                    batch = []
                    
            except json.JSONDecodeError:
                total_skipped += 1
            except Exception as e:
                total_skipped += 1
    
    # 插入剩余
    if batch:
        cursor.executemany(insert_sql, batch)
        conn.commit()
        total_inserted += len(batch)
    
    print(f"\n  导入完成！已处理 {total_inserted} 条, 跳过 {total_skipped} 条")
    
    # 验证
    cursor.execute('SELECT COUNT(*) FROM pr_data')
    final_count = cursor.fetchone()[0]
    print(f"  数据库最终记录数: {final_count}")
    print(f"  新增记录: {final_count - existing_count}")
    
    # 确保索引还存在
    print("  创建/确认索引...")
    try:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_type ON pr_data (type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_year_month ON pr_data (year_month)')
    except:
        pass
    conn.commit()
    
    conn.close()
    print("  全部完成！")

if __name__ == "__main__":
    main()