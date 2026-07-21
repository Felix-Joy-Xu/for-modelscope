"""合并 BOSS 数据：jsonl → DB → CSV 完整输出"""
import os, json, csv, sqlite3

base = r'D:\hiring_data\boss_api'
JL = os.path.join(base, 'boss_jd_full.jsonl')
DB = os.path.join(base, 'boss_jobs.db')
OUT_CSV = os.path.join(base, 'boss_jobs_final.csv')

print("=" * 60)
print("=== BOSS 数据合并 ===")
print("=" * 60)

# ======== 1. jsonl 汇总 ========
print("\n[1/3] 汇总 jsonl (去重取最新)...")
jl_data = {}
dup = 0
with open(JL, 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            jid = d.get('encryptJobId', '').strip()
            if not jid:
                continue
            # 保留最后一个（最新的）
            jl_data[jid] = d.get('jd_text', '')
        except:
            pass
print(f"  jsonl 有效记录: {len(jl_data)}")

# ======== 2. 更新 DB ========
print("\n[2/3] 更新数据库...")
conn = sqlite3.connect(DB)
cur = conn.cursor()

# 确保 jd_text 和 jd_len 列存在
try:
    cur.execute("ALTER TABLE jobs ADD COLUMN jd_text TEXT")
except:
    pass
try:
    cur.execute("ALTER TABLE jobs ADD COLUMN jd_len INTEGER")
except:
    pass

# 确保所有 CSV 职位都在 DB 中
CP = os.path.join(base, 'boss_jobs_cleaned.csv')
csv_cols = []
csv_rows = []

# 先确保基础表里有 encryptJobId 索引
cur.execute("CREATE INDEX IF NOT EXISTS idx_jid ON jobs(encryptJobId)")

updated = 0
skipped = 0
for jid, jd_text in jl_data.items():
    if jd_text and len(jd_text) > 50:
        cur.execute(
            "UPDATE jobs SET jd_text = ?, jd_len = ? WHERE encryptJobId = ?",
            (jd_text, len(jd_text), jid)
        )
        if cur.rowcount > 0:
            updated += 1
        else:
            skipped += 1

conn.commit()
print(f"  DB 更新: {updated} 条, 未匹配(跳过): {skipped} 条")

# 最终 jd_text 填充率
cur.execute("SELECT COUNT(*) FROM jobs WHERE jd_text IS NOT NULL AND jd_text != ''")
jd_ok = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM jobs")
total = cur.fetchone()[0]
print(f"  DB 总行: {total}, jd_text 已填充: {jd_ok} ({jd_ok/total*100:.1f}%)")

# ======== 3. 导出完整 CSV ========
print(f"\n[3/3] 导出完整 CSV → {OUT_CSV} ...")

cur.execute("SELECT * FROM jobs LIMIT 1")
all_cols = [d[0] for d in cur.description]

cur.execute("SELECT * FROM jobs")
with open(OUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(all_cols)
    count = 0
    for row in cur:
        w.writerow(row)
        count += 1

conn.close()
print(f"  导出完成: {count} 行, {len(all_cols)} 列")
sz = os.path.getsize(OUT_CSV)
print(f"  文件大小: {sz/1024/1024:.1f}MB")
print(f"\n=== 合并完成 ===")