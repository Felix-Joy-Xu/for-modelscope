"""BOSS 数据库 — 工资分布深度分析"""
import sqlite3
from collections import defaultdict

DB = r'D:\hiring_data\boss_api\boss_jobs.db'

print("=" * 70)
print("=== BOSS 直聘 — 工资分布深度分析 ===")
print("=" * 70)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# ═══════════════════════════════════════════
# 基础：salary_avg_k 有值样本
# ═══════════════════════════════════════════
cur.execute("SELECT COUNT(*) FROM jobs WHERE CAST(salary_avg_k AS REAL) > 0")
n_sal = cur.fetchone()[0]
print(f"\n有效薪资样本: {n_sal:,} / 72,026 ({n_sal/72026*100:.1f}%)")

# ═══════════════════════════════════════════
# 1. 细粒度薪资直方图（每 2k 一档）
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【1. 平均薪资直方图 (每 2k)】")
hist_bins = list(range(0, 120, 2))
for i, lo in enumerate(hist_bins[:-1]):
    hi = hist_bins[i + 1]
    cur.execute(f"SELECT COUNT(*) FROM jobs WHERE CAST(salary_avg_k AS REAL) > {lo} AND CAST(salary_avg_k AS REAL) <= {hi}")
    c = cur.fetchone()[0]
    if c == 0:
        continue
    bar = '█' * max(1, c * 80 // n_sal)
    pct = c / n_sal * 100
    print(f"  {lo:>3}-{hi:>3}k: {c:>5,} ({pct:4.1f}%) {bar}")

# 100k+
cur.execute("SELECT COUNT(*) FROM jobs WHERE CAST(salary_avg_k AS REAL) > 100")
c = cur.fetchone()[0]
print(f"  100k+: {c:>5,} ({c/n_sal*100:4.1f}%) {'█' * max(1, c * 80 // n_sal)}")

# ═══════════════════════════════════════════
# 2. 分位数详细
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【2. 薪资分位数 (salary_avg_k)】")
for pct in [1, 5, 10, 25, 40, 50, 60, 75, 80, 90, 95, 97, 99]:
    offset = max(0, n_sal * pct // 100 - 1)
    cur.execute(f"SELECT CAST(salary_avg_k AS REAL) FROM jobs WHERE CAST(salary_avg_k AS REAL) > 0 ORDER BY CAST(salary_avg_k AS REAL) LIMIT 1 OFFSET {offset}")
    row = cur.fetchone()
    val = row[0] if row else 0
    print(f"  P{pct:>2d}: {val:>6.1f}k")

# 均值、标准差（用 SQLite 近似）
cur.execute("SELECT AVG(CAST(salary_avg_k AS REAL)) FROM jobs WHERE CAST(salary_avg_k AS REAL) > 0")
mean_sal = cur.fetchone()[0]
print(f"\n  均值: {mean_sal:.1f}k")

# ═══════════════════════════════════════════
# 3. 薪资 × 城市
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【3. 各城市薪资统计】")
cities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', '南京', '苏州']
print(f"  {'城市':<8s} {'数量':>5s}  {'均值':>6s}  {'P25':>6s}  {'P50':>6s}  {'P75':>6s}  {'P90':>6s}  {'P95':>6s}")
print(f"  {'-'*8} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for city in cities:
    cur.execute(f"SELECT COUNT(*), AVG(CAST(salary_avg_k AS REAL)) FROM jobs WHERE city = ? AND CAST(salary_avg_k AS REAL) > 0", (city,))
    cnt, avg = cur.fetchone()
    if cnt == 0:
        continue
    pcts = []
    for pct in [25, 50, 75, 90, 95]:
        offset = max(0, int(cnt * pct / 100) - 1)
        cur.execute(f"SELECT CAST(salary_avg_k AS REAL) FROM jobs WHERE city = ? AND CAST(salary_avg_k AS REAL) > 0 ORDER BY CAST(salary_avg_k AS REAL) LIMIT 1 OFFSET {offset}", (city,))
        row = cur.fetchone()
        pcts.append(row[0] if row else 0)
    print(f"  {city:<8s} {cnt:>5,}  {avg:>5.0f}k  {pcts[0]:>5.0f}k  {pcts[1]:>5.0f}k  {pcts[2]:>5.0f}k  {pcts[3]:>5.0f}k  {pcts[4]:>5.0f}k")

# ═══════════════════════════════════════════
# 4. 薪资 × 经验
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【4. 各经验要求薪资】")
exp_levels = ['经验不限', '在校/应届', '应届生', '1年以内', '1-3年', '3-5年', '5-10年', '10年以上']
print(f"  {'经验':<12s} {'数量':>5s}  {'均值':>6s}  {'P25':>6s}  {'P50':>6s}  {'P75':>6s}  {'P90':>6s}")
print(f"  {'-'*12} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for exp in exp_levels:
    cur.execute(f"SELECT COUNT(*), AVG(CAST(salary_avg_k AS REAL)) FROM jobs WHERE jobExperience = ? AND CAST(salary_avg_k AS REAL) > 0", (exp,))
    cnt, avg = cur.fetchone()
    if cnt == 0:
        continue
    pcts = []
    for pct in [25, 50, 75, 90]:
        offset = max(0, int(cnt * pct / 100) - 1)
        cur.execute(f"SELECT CAST(salary_avg_k AS REAL) FROM jobs WHERE jobExperience = ? AND CAST(salary_avg_k AS REAL) > 0 ORDER BY CAST(salary_avg_k AS REAL) LIMIT 1 OFFSET {offset}", (exp,))
        row = cur.fetchone()
        pcts.append(row[0] if row else 0)
    print(f"  {exp:<12s} {cnt:>5,}  {avg:>5.0f}k  {pcts[0]:>5.0f}k  {pcts[1]:>5.0f}k  {pcts[2]:>5.0f}k  {pcts[3]:>5.0f}k")

# ═══════════════════════════════════════════
# 5. 薪资 × 学历
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【5. 各学历薪资】")
degree_order = ['学历不限', '初中及以下', '高中', '中专/中技', '大专', '本科', '硕士', '博士']
print(f"  {'学历':<12s} {'数量':>5s}  {'均值':>6s}  {'P25':>6s}  {'P50':>6s}  {'P75':>6s}  {'P90':>6s}")
print(f"  {'-'*12} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for deg in degree_order:
    cur.execute(f"SELECT COUNT(*), AVG(CAST(salary_avg_k AS REAL)) FROM jobs WHERE jobDegree = ? AND CAST(salary_avg_k AS REAL) > 0", (deg,))
    cnt, avg = cur.fetchone()
    if cnt == 0:
        continue
    pcts = []
    for pct in [25, 50, 75, 90]:
        offset = max(0, int(cnt * pct / 100) - 1)
        cur.execute(f"SELECT CAST(salary_avg_k AS REAL) FROM jobs WHERE jobDegree = ? AND CAST(salary_avg_k AS REAL) > 0 ORDER BY CAST(salary_avg_k AS REAL) LIMIT 1 OFFSET {offset}", (deg,))
        row = cur.fetchone()
        pcts.append(row[0] if row else 0)
    print(f"  {deg:<12s} {cnt:>5,}  {avg:>5.0f}k  {pcts[0]:>5.0f}k  {pcts[1]:>5.0f}k  {pcts[2]:>5.0f}k  {pcts[3]:>5.0f}k")

# ═══════════════════════════════════════════
# 6. 薪资 × 行业 Top 15
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【6. 各行业薪资 Top 20】")
cur.execute("""
    SELECT brandIndustry, COUNT(*) as cnt, AVG(CAST(salary_avg_k AS REAL)) as avg_sal
    FROM jobs
    WHERE brandIndustry IS NOT NULL AND brandIndustry != '' AND CAST(salary_avg_k AS REAL) > 0
    GROUP BY brandIndustry
    HAVING cnt >= 50
    ORDER BY avg_sal DESC
    LIMIT 20
""")
print(f"  {'行业':<30s} {'数量':>5s}  {'均值薪资':>6s}")
print(f"  {'-'*30} {'-'*5} {'-'*6}")
for row in cur.fetchall():
    ind, cnt, avg = row
    print(f"  {ind[:30]:30s} {cnt:>5,}  {avg:>5.0f}k")

# ═══════════════════════════════════════════
# 7. 薪资 × 公司规模
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【7. 各公司规模薪资】")
scale_order = ['0-20人', '20-99人', '100-499人', '500-999人', '1000-9999人', '10000人以上']
print(f"  {'规模':<16s} {'数量':>5s}  {'均值':>6s}  {'P25':>6s}  {'P50':>6s}  {'P75':>6s}  {'P90':>6s}")
print(f"  {'-'*16} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for sc in scale_order:
    cur.execute(f"SELECT COUNT(*), AVG(CAST(salary_avg_k AS REAL)) FROM jobs WHERE brandScaleName = ? AND CAST(salary_avg_k AS REAL) > 0", (sc,))
    cnt, avg = cur.fetchone()
    if cnt == 0:
        continue
    pcts = []
    for pct in [25, 50, 75, 90]:
        offset = max(0, int(cnt * pct / 100) - 1)
        cur.execute(f"SELECT CAST(salary_avg_k AS REAL) FROM jobs WHERE brandScaleName = ? AND CAST(salary_avg_k AS REAL) > 0 ORDER BY CAST(salary_avg_k AS REAL) LIMIT 1 OFFSET {offset}", (sc,))
        row = cur.fetchone()
        pcts.append(row[0] if row else 0)
    print(f"  {sc:<16s} {cnt:>5,}  {avg:>5.0f}k  {pcts[0]:>5.0f}k  {pcts[1]:>5.0f}k  {pcts[2]:>5.0f}k  {pcts[3]:>5.0f}k")

# ═══════════════════════════════════════════
# 8. 薪资 × 发展阶段
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【8. 各发展阶段公司薪资】")
stage_order = ['未融资', '不需要融资', '天使轮', 'A轮', 'B轮', 'C轮', 'D轮及以上', '已上市']
print(f"  {'阶段':<12s} {'数量':>5s}  {'均值':>6s}  {'P25':>6s}  {'P50':>6s}  {'P75':>6s}  {'P90':>6s}")
print(f"  {'-'*12} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*6}")
for st in stage_order:
    cur.execute(f"SELECT COUNT(*), AVG(CAST(salary_avg_k AS REAL)) FROM jobs WHERE brandStageName = ? AND CAST(salary_avg_k AS REAL) > 0", (st,))
    cnt, avg = cur.fetchone()
    if cnt == 0:
        continue
    pcts = []
    for pct in [25, 50, 75, 90]:
        offset = max(0, int(cnt * pct / 100) - 1)
        cur.execute(f"SELECT CAST(salary_avg_k AS REAL) FROM jobs WHERE brandStageName = ? AND CAST(salary_avg_k AS REAL) > 0 ORDER BY CAST(salary_avg_k AS REAL) LIMIT 1 OFFSET {offset}", (st,))
        row = cur.fetchone()
        pcts.append(row[0] if row else 0)
    print(f"  {st:<12s} {cnt:>5,}  {avg:>5.0f}k  {pcts[0]:>5.0f}k  {pcts[1]:>5.0f}k  {pcts[2]:>5.0f}k  {pcts[3]:>5.0f}k")

# ═══════════════════════════════════════════
# 9. 高薪职位 Top 30（平均薪资）
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【9. 高薪职位类型 Top 30 (按均值, ≥50条)】")
cur.execute("""
    SELECT jobName, COUNT(*) as cnt, AVG(CAST(salary_avg_k AS REAL)) as avg_sal,
           MIN(CAST(salary_avg_k AS REAL)), MAX(CAST(salary_avg_k AS REAL))
    FROM jobs
    WHERE jobName IS NOT NULL AND CAST(salary_avg_k AS REAL) > 0
    GROUP BY jobName
    HAVING cnt >= 20
    ORDER BY avg_sal DESC
    LIMIT 30
""")
print(f"  {'职位':<35s} {'数量':>5s}  {'均值':>6s}  {'范围':>12s}")
print(f"  {'-'*35} {'-'*5} {'-'*6} {'-'*12}")
for row in cur.fetchall():
    jn, cnt, avg, mn, mx = row
    print(f"  {jn[:35]:35s} {cnt:>5,}  {avg:>5.0f}k  {mn:>4.0f}-{mx:>4.0f}k")

# ═══════════════════════════════════════════
# 10. salary_min vs salary_max 对比
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【10. 薪资范围 (min vs max vs avg)】")
cur.execute("""
    SELECT AVG(CAST(salary_min_k AS REAL)), AVG(CAST(salary_max_k AS REAL)), AVG(CAST(salary_avg_k AS REAL))
    FROM jobs WHERE CAST(salary_avg_k AS REAL) > 0
""")
mn_avg, mx_avg, avg_avg = cur.fetchone()
print(f"  salary_min 均值:  {mn_avg:.1f}k")
print(f"  salary_avg 均值:  {avg_avg:.1f}k")
print(f"  salary_max 均值:  {mx_avg:.1f}k")
print(f"  平均薪资范围跨度: {mn_avg:.0f}k - {mx_avg:.0f}k (中位差距 {mx_avg-mn_avg:.0f}k)")

# spread ratio
cur.execute("SELECT AVG(CAST(salary_max_k AS REAL)/CAST(salary_min_k AS REAL)) FROM jobs WHERE CAST(salary_min_k AS REAL) > 1 AND CAST(salary_max_k AS REAL) > 1")
ratio = cur.fetchone()[0]
print(f"  薪资 max/min 比均值: {ratio:.2f}x")

# ═══════════════════════════════════════════
# 11. 薪资月数对应的年薪估算
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【11. 年薪估算 (salary_avg_k × months)】")
cur.execute("""
    SELECT AVG(CAST(salary_avg_k AS REAL) * CAST(months AS REAL)),
           AVG(CAST(salary_avg_k AS REAL) * 12)
    FROM jobs
    WHERE CAST(months AS REAL) > 0 AND CAST(salary_avg_k AS REAL) > 0
""")
est_annual, base_12m = cur.fetchone()
print(f"  按12个月基础年薪均值: {base_12m/10:.1f}万")
print(f"  按实际月数年薪均值:   {est_annual/10:.1f}万")
cur.execute("SELECT COUNT(*) FROM jobs WHERE CAST(months AS REAL) > 12")
more_12 = cur.fetchone()[0]
print(f"  超过12薪的职位: {more_12:,} ({more_12/n_sal*100:.1f}%)")

# ═══════════════════════════════════════════
# 12. 雇主薪资 Top 20
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【12. 雇主薪资 Top 20 (≥30条)】")
cur.execute("""
    SELECT brandName, COUNT(*) as cnt, AVG(CAST(salary_avg_k AS REAL)) as avg_sal
    FROM jobs
    WHERE brandName IS NOT NULL AND brandName != '' AND CAST(salary_avg_k AS REAL) > 0
    GROUP BY brandName
    HAVING cnt >= 30
    ORDER BY avg_sal DESC
    LIMIT 20
""")
print(f"  {'雇主':<30s} {'数量':>5s}  {'均值薪资':>6s}")
print(f"  {'-'*30} {'-'*5} {'-'*6}")
for row in cur.fetchall():
    name, cnt, avg = row
    print(f"  {name[:30]:30s} {cnt:>5,}  {avg:>5.0f}k")

print("\n" + "=" * 70)
print("=== 工资分布分析完成 ===")
conn.close()