"""统计所有 BOSS 数据文件的 JD 总量"""
import json, csv, os, sqlite3
base = r'D:\hiring_data\boss_api'

print("=" * 60)
print("=== BOSS JD 全量统计 ===")
print("=" * 60)

# 1. boss_jobs_final.csv (最新合并)
fp = os.path.join(base, 'boss_jobs_final.csv')
if os.path.exists(fp):
    with open(fp, 'r', encoding='utf-8-sig', errors='replace') as f:
        r = csv.reader(f)
        h = next(r)
        jd_idx = h.index('jd_text')
        rows_c = list(r)
    csv_total = len(rows_c)
    csv_with_jd = sum(1 for r in rows_c if r[jd_idx] and len(r[jd_idx]) > 50)
    print(f'\n[1] boss_jobs_final.csv')
    print(f'    总行数: {csv_total:,}')
    print(f'    含JD(>50字): {csv_with_jd:,} ({csv_with_jd/csv_total*100:.1f}%)')
else:
    print('\n[1] boss_jobs_final.csv — 不存在')

# 2. boss_jd_full.jsonl
jl = os.path.join(base, 'boss_jd_full.jsonl')
if os.path.exists(jl):
    jl_total = sum(1 for _ in open(jl, 'r', encoding='utf-8', errors='replace'))
    jl_with_jd = 0
    with open(jl, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                txt = d.get('jd_text', '')
                if txt and len(txt) > 50:
                    jl_with_jd += 1
            except:
                pass
    print(f'\n[2] boss_jd_full.jsonl')
    print(f'    总行数: {jl_total:,}')
    print(f'    含JD(>50字): {jl_with_jd:,}')
else:
    print('\n[2] boss_jd_full.jsonl — 不存在')

# 3. boss_jobs.db
dp = os.path.join(base, 'boss_jobs.db')
if os.path.exists(dp):
    conn = sqlite3.connect(dp)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM jobs')
    db_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM jobs WHERE jd_text IS NOT NULL AND jd_text != ''")
    db_with_jd = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM jobs WHERE jd_text IS NOT NULL AND length(jd_text) > 50")
    db_with_jd_50 = cur.fetchone()[0]
    conn.close()
    print(f'\n[3] boss_jobs.db')
    print(f'    总行数: {db_total:,}')
    print(f'    含JD(非空): {db_with_jd:,} ({db_with_jd/db_total*100:.1f}%)')
    print(f'    含JD(>50字): {db_with_jd_50:,} ({db_with_jd_50/db_total*100:.1f}%)')
else:
    print('\n[3] boss_jobs.db — 不存在')

# 4. boss_jobs_cleaned.csv (原始)
cp = os.path.join(base, 'boss_jobs_cleaned.csv')
if os.path.exists(cp):
    with open(cp, 'r', encoding='utf-8', errors='replace') as f:
        r = csv.reader(f)
        h2 = next(r)
        jd2 = h2.index('jd_text')
        rows_cc = list(r)
    cc_total = len(rows_cc)
    cc_with_jd = sum(1 for r in rows_cc if r[jd2] and len(r[jd2]) > 50)
    print(f'\n[4] boss_jobs_cleaned.csv (原始)')
    print(f'    总行数: {cc_total:,}')
    print(f'    含JD(>50字): {cc_with_jd:,} ({cc_with_jd/cc_total*100:.1f}%)')
else:
    print('\n[4] boss_jobs_cleaned.csv — 不存在')

print(f'\n{"=" * 60}')
print(f'=== 汇总 ===')
summaries = []
if os.path.exists(fp):
    summaries.append(('boss_jobs_final.csv', csv_total, csv_with_jd))
if os.path.exists(jl):
    summaries.append(('boss_jd_full.jsonl', jl_total, jl_with_jd))
if os.path.exists(dp):
    summaries.append(('boss_jobs.db', db_total, db_with_jd_50))
if os.path.exists(cp):
    summaries.append(('boss_jobs_cleaned.csv', cc_total, cc_with_jd))
for name, total, jd in summaries:
    print(f'  {name:30s}  {jd:,} JD / {total:,} 职位  ({jd/total*100:.1f}%)')