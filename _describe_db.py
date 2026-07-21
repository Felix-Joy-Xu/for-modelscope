"""BOSS 数据库描述性统计"""
import sqlite3, os
from collections import Counter

DB = r'D:\hiring_data\boss_api\boss_jobs.db'

print("=" * 70)
print("=== BOSS 直聘数据库 — 描述性统计 ===")
print("=" * 70)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# ═══════════════════════════════════════════
# 1. 基础总量
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【1. 基础总量】")
cur.execute("SELECT COUNT(*) FROM jobs")
total = cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT encryptJobId) FROM jobs")
uniq = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM jobs WHERE jd_text IS NOT NULL AND length(jd_text) > 50")
jd_ok = cur.fetchone()[0]
cur.execute("SELECT AVG(jd_len), MIN(jd_len), MAX(jd_len), "
            "AVG(CASE WHEN jd_len>50 THEN jd_len END) "
            "FROM jobs")
jd_avg, jd_min, jd_max, jd_avg_valid = cur.fetchone()
print(f"  职位总数:        {total:,}")
print(f"  唯一ID:          {uniq:,}")
print(f"  含有效JD(>50字): {jd_ok:,} ({jd_ok/total*100:.1f}%)")
print(f"  JD长度:          均值={jd_avg:.0f}字, 中位=", end="")
cur.execute("SELECT jd_len FROM jobs WHERE jd_len>50 ORDER BY jd_len LIMIT 1 OFFSET (SELECT COUNT(*) FROM jobs WHERE jd_len>50)/2")
med = cur.fetchone()
print(f"{med[0] if med else 'N/A'}字, 范围={jd_min}-{jd_max}字")

# ═══════════════════════════════════════════
# 2. 薪资分布
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【2. 薪资分布 (K/月)】")

for col, label in [('salary_min_k', '最低薪资'), ('salary_max_k', '最高薪资'), ('salary_avg_k', '平均薪资')]:
    cur.execute(f"SELECT COUNT(*), AVG(CAST({col} AS REAL)), MIN(CAST({col} AS REAL)), MAX(CAST({col} AS REAL)) FROM jobs WHERE CAST({col} AS REAL) > 1")
    n, avg_m, mn_m, mx_m = cur.fetchone()
    cur.execute(f"SELECT CAST({col} AS REAL) FROM jobs WHERE CAST({col} AS REAL) > 1 ORDER BY CAST({col} AS REAL) LIMIT 1 OFFSET {n//2}")
    med_m = cur.fetchone()[0]
    cur.execute(f"SELECT CAST({col} AS REAL) FROM jobs WHERE CAST({col} AS REAL) > 1 ORDER BY CAST({col} AS REAL) LIMIT 1 OFFSET {n//4}")
    q1 = cur.fetchone()[0]
    cur.execute(f"SELECT CAST({col} AS REAL) FROM jobs WHERE CAST({col} AS REAL) > 1 ORDER BY CAST({col} AS REAL) LIMIT 1 OFFSET {3*n//4}")
    q3 = cur.fetchone()[0]
    print(f"  {label:8s}: 均值={avg_m:.1f}k, 中位={med_m:.0f}k, Q1={q1:.0f}k, Q3={q3:.0f}k, 范围={mn_m:.0f}-{mx_m:.0f}k (n={n:,})")

# salary_avg_k 分层
print(f"\n  平均薪资分层:")
bins = [(0,5), (5,10), (10,15), (15,20), (20,25), (25,30), (30,40), (40,60), (60,100), (100,9999)]
for lo, hi in bins:
    cur.execute(f"SELECT COUNT(*) FROM jobs WHERE CAST(salary_avg_k AS REAL) > {lo} AND CAST(salary_avg_k AS REAL) <= {hi}")
    c = cur.fetchone()[0]
    bar = '█' * (c * 50 // total)
    print(f"    {lo:>4}-{hi:>4}k: {c:>6,} ({c/total*100:5.1f}%) {bar}")

# ═══════════════════════════════════════════
# 3. 经验要求
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【3. 经验要求】")
cur.execute("SELECT jobExperience, COUNT(*) as cnt FROM jobs WHERE jobExperience IS NOT NULL AND jobExperience != '' GROUP BY jobExperience ORDER BY cnt DESC LIMIT 10")
for row in cur.fetchall():
    print(f"  {row[0]:20s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%)")

cur.execute("SELECT AVG(CAST(exp_min_year AS REAL)), AVG(CAST(exp_max_year AS REAL)), MIN(CAST(exp_min_year AS REAL)), MAX(CAST(exp_max_year AS REAL)) FROM jobs WHERE CAST(exp_min_year AS REAL) > 0")
avg_exp_min, avg_exp_max, mn_exp, mx_exp = cur.fetchone()
print(f"  经验年限(min): 均值={avg_exp_min:.1f}年, 范围={mn_exp:.0f}-{mx_exp:.0f}年")
print(f"  经验年限(max): 均值={avg_exp_max:.1f}年")

# ═══════════════════════════════════════════
# 4. 学历要求
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【4. 学历要求】")
cur.execute("SELECT jobDegree, COUNT(*) as cnt FROM jobs WHERE jobDegree IS NOT NULL AND jobDegree != '' GROUP BY jobDegree ORDER BY cnt DESC")
for row in cur.fetchall():
    print(f"  {row[0]:20s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 5. 城市分布
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【5. 城市分布 Top 20】")
cur.execute("SELECT city, COUNT(*) as cnt FROM jobs WHERE city IS NOT NULL AND city != '' GROUP BY city ORDER BY cnt DESC LIMIT 20")
for row in cur.fetchall():
    bar = '█' * (row[1] * 50 // total)
    print(f"  {row[0]:12s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%) {bar}")

cur.execute("SELECT COUNT(DISTINCT city) FROM jobs WHERE city IS NOT NULL AND city != ''")
print(f"  城市总数: {cur.fetchone()[0]}")

# ═══════════════════════════════════════════
# 6. 行业分布
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【6. 行业分布 Top 20】")
cur.execute("SELECT brandIndustry, COUNT(*) as cnt FROM jobs WHERE brandIndustry IS NOT NULL AND brandIndustry != '' GROUP BY brandIndustry ORDER BY cnt DESC LIMIT 20")
for row in cur.fetchall():
    print(f"  {row[0][:30]:30s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 7. 公司规模
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【7. 公司规模分布】")
cur.execute("SELECT brandScaleName, COUNT(*) as cnt FROM jobs WHERE brandScaleName IS NOT NULL AND brandScaleName != '' GROUP BY brandScaleName ORDER BY cnt DESC")
for row in cur.fetchall():
    print(f"  {row[0]:20s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 8. 公司发展阶段
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【8. 公司发展阶段】")
cur.execute("SELECT brandStageName, COUNT(*) as cnt FROM jobs WHERE brandStageName IS NOT NULL AND brandStageName != '' GROUP BY brandStageName ORDER BY cnt DESC")
for row in cur.fetchall():
    print(f"  {row[0]:20s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 9. 雇主 Top 20
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【9. 雇主 Top 20】")
cur.execute("SELECT brandName, COUNT(*) as cnt FROM jobs WHERE brandName IS NOT NULL AND brandName != '' GROUP BY brandName ORDER BY cnt DESC LIMIT 20")
for row in cur.fetchall():
    print(f"  {row[0][:25]:25s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 10. 职位类型
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【10. 职位类型】")
cur.execute("SELECT jobTypeDesc, COUNT(*) as cnt FROM jobs WHERE jobTypeDesc IS NOT NULL AND jobTypeDesc != '' GROUP BY jobTypeDesc ORDER BY cnt DESC LIMIT 10")
for row in cur.fetchall():
    print(f"  {row[0]:20s}: {row[1]:>6,} ({row[1]/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 11. 高频技能
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【11. 高频技能 Top 25】")
skill_counter = Counter()
cur.execute("SELECT skills FROM jobs WHERE skills IS NOT NULL AND skills != ''")
for (s,) in cur.fetchall():
    for sk in s.split(','):
        sk = sk.strip().strip("[]'\" ").strip()
        if sk and sk not in ('', '[]', 'null', 'None'):
            skill_counter[sk] += 1
for sk, cnt in skill_counter.most_common(25):
    print(f"  {sk[:30]:30s}: {cnt:>6,} ({cnt/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 12. 高频职位标签
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【12. 高频职位标签 Top 25】")
label_counter = Counter()
cur.execute("SELECT jobLabels FROM jobs WHERE jobLabels IS NOT NULL AND jobLabels != ''")
for (s,) in cur.fetchall():
    for lb in s.split(','):
        lb = lb.strip().strip("[]'\" ").strip()
        if lb and lb not in ('', '[]', 'null', 'None'):
            label_counter[lb] += 1
for lb, cnt in label_counter.most_common(25):
    print(f"  {lb[:30]:30s}: {cnt:>6,} ({cnt/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 13. 职位名称 Top 20
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【13. 职位名称 Top 20】")
cur.execute("SELECT jobName, COUNT(*) as cnt FROM jobs WHERE jobName IS NOT NULL AND jobName != '' GROUP BY jobName ORDER BY cnt DESC LIMIT 20")
for row in cur.fetchall():
    print(f"  {row[0][:35]:35s}: {row[1]:>5,}")

# ═══════════════════════════════════════════
# 14. Boss 头衔 Top 10
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【14. 招聘者头衔 Top 15】")
cur.execute("SELECT bossTitle, COUNT(*) as cnt FROM jobs WHERE bossTitle IS NOT NULL AND bossTitle != '' GROUP BY bossTitle ORDER BY cnt DESC LIMIT 15")
for row in cur.fetchall():
    print(f"  {row[0][:30]:30s}: {row[1]:>6,}")

# ═══════════════════════════════════════════
# 15. 月份数分布 (薪资月数)
# ═══════════════════════════════════════════
print("\n" + "─" * 50)
print("【15. 薪资月数】")
cur.execute("SELECT CAST(months AS REAL), COUNT(*) as cnt FROM jobs WHERE CAST(months AS REAL) > 0 GROUP BY months ORDER BY CAST(months AS REAL)")
for row in cur.fetchall():
    m = float(row[0])
    print(f"  {m:.0f}个月: {int(row[1]):>6,} ({int(row[1])/total*100:5.1f}%)")

# ═══════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print("=== 描述性统计完成 ===")
print(f"数据库: {DB}  ({os.path.getsize(DB)/1024/1024:.1f}MB)")
print(f"表: jobs  |  {total:,} 行  |  26 列")
print("=" * 70)

conn.close()