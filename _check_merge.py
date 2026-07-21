"""检查 BOSS 数据文件现状，确认合并目标"""
import os, json, csv, sqlite3
base = r'D:\hiring_data\boss_api'

# 文件大小
for f in ['boss_jd_full.jsonl', 'boss_jobs_cleaned.csv', 'boss_jobs.db']:
    p = os.path.join(base, f)
    if os.path.exists(p):
        sz = os.path.getsize(p)
        print(f'{f}: {sz/1024/1024:.1f}MB')
    else:
        print(f'{f}: 不存在')

# jsonl 总行数
jl = os.path.join(base, 'boss_jd_full.jsonl')
if os.path.exists(jl):
    n = sum(1 for _ in open(jl, 'r', encoding='utf-8', errors='replace'))
    print(f'\nboss_jd_full.jsonl 行数: {n}')

# CSV 列名+行数
cp = os.path.join(base, 'boss_jobs_cleaned.csv')
if os.path.exists(cp):
    with open(cp, 'r', encoding='utf-8', errors='replace') as f:
        r = csv.reader(f)
        h = next(r)
        rows = sum(1 for _ in r)
    print(f'boss_jobs_cleaned.csv: {rows} 行, 列={h[:10]}...')

# DB 表结构+行数
dp = os.path.join(base, 'boss_jobs.db')
if os.path.exists(dp):
    conn = sqlite3.connect(dp)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cur.fetchall()]
    print(f'\nDB 表: {tables}')
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        cur.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cur.fetchall()]
        print(f'  {t}: {cnt} 行, 列={cols}')

    # 检查 jd_text 填充率
    cur.execute("SELECT COUNT(*) FROM jobs WHERE jd_text IS NOT NULL AND jd_text != ''")
    jd_ok = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM jobs")
    total = cur.fetchone()[0]
    print(f'  jd_text 已填充: {jd_ok}/{total} ({jd_ok/total*100:.1f}%)')

    # 查几条样例看看 jd_text 是不是已经和 CSV 内容合并了
    cur.execute("SELECT encryptJobId, jobName, jd_text FROM jobs WHERE jd_text IS NOT NULL AND jd_text != '' LIMIT 3")
    for row in cur.fetchall():
        print(f'  样例: {row[0][:20]}... | {row[1]} | jd_text={len(row[2] if row[2] else "")}字')
    conn.close()