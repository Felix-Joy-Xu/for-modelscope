"""将去重后的 boss_jobs_final_dedup.csv 导入 SQLite，建立索引"""
import csv, sqlite3, os, time

SRC = r'D:\hiring_data\boss_api\boss_jobs_final_dedup.csv'
DB  = r'D:\hiring_data\boss_api\boss_jobs.db'

print("=" * 60)
print("=== 重建 BOSS SQLite 数据库 ===")
print("=" * 60)

# 读取 CSV
t0 = time.time()
with open(SRC, 'r', encoding='utf-8-sig', errors='replace') as f:
    r = csv.reader(f)
    header = next(r)
    rows = list(r)
print(f"\n[1/3] 读取 CSV: {len(rows)} 行, {len(header)} 列 ({time.time()-t0:.1f}s)")

# 连接数据库（替换旧表）
t0 = time.time()
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS jobs")

# 推断列类型，建表
col_defs = []
for col in header:
    col_clean = col.strip().replace('"', '').replace("'", '')
    if col_clean in ('jd_text', 'jobDesc_short', 'salaryDesc', 'jobLabels', 'skills',
                      'jobName', 'city', 'areaDistrict', 'businessDistrict',
                      'jobDegree', 'jobExperience', 'brandName', 'brandIndustry',
                      'brandScaleName', 'brandStageName', 'bossName', 'bossTitle',
                      'jobTypeDesc', 'encryptJobId'):
        col_defs.append(f'"{col_clean}" TEXT')
    elif col_clean in ('salary_min_k', 'salary_max_k', 'salary_avg_k', 'months',
                        'exp_min_year', 'exp_max_year', 'jd_len'):
        col_defs.append(f'"{col_clean}" REAL')
    else:
        col_defs.append(f'"{col_clean}" TEXT')

create_sql = f'CREATE TABLE jobs ({", ".join(col_defs)})'
cur.execute(create_sql)
print(f"[2/3] 建表: jobs ({len(col_defs)} 列)")

# 批量插入
t0 = time.time()
placeholders = ','.join(['?'] * len(header))
cols_quoted = ','.join([f'"{c.strip()}"' for c in header])
insert_sql = f'INSERT INTO jobs ({cols_quoted}) VALUES ({placeholders})'

batch_size = 5000
for i in range(0, len(rows), batch_size):
    batch = rows[i:i+batch_size]
    cur.executemany(insert_sql, batch)
    if i % 20000 == 0:
        print(f"  插入 {min(i+batch_size, len(rows))}/{len(rows)} ...")
conn.commit()
print(f"[3/3] 插入完成 ({time.time()-t0:.1f}s)")

# 建索引
print(f"\n建立索引...")
cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_encryptJobId ON jobs(encryptJobId)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_jobName ON jobs(jobName)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_city ON jobs(city)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_brandName ON jobs(brandName)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_brandIndustry ON jobs(brandIndustry)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_salary_avg ON jobs(salary_avg_k)')
cur.execute('CREATE INDEX IF NOT EXISTS idx_exp_min ON jobs(exp_min_year)')
conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM jobs")
cnt = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM jobs WHERE jd_text IS NOT NULL AND length(jd_text) > 50")
jd_cnt = cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT encryptJobId) FROM jobs")
uniq = cur.fetchone()[0]

sz = os.path.getsize(DB)
print(f"\n{'='*60}")
print(f"数据库: {DB}")
print(f"大小: {sz/1024/1024:.1f}MB")
print(f"总行数: {cnt:,}")
print(f"含有效JD: {jd_cnt:,} ({jd_cnt/cnt*100:.1f}%)")
print(f"ID唯一: {cnt} == {uniq} {'✅' if cnt == uniq else '❌'}")

# 抽样
cur.execute("SELECT encryptJobId, jobName, city, salary_avg_k FROM jobs LIMIT 3")
print(f"\n样例:")
for row in cur.fetchall():
    print(f"  {row[0][:20]}... | {row[1][:15]} | {row[2]} | {row[3]}k")

conn.close()
print(f"\n=== 数据库重建完成 ===")