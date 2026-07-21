"""BOSS 数据去重：按 jd_text 内容去重，保留第一次出现的记录"""
import csv, os

base = r'D:\hiring_data\boss_api'
SRC = os.path.join(base, 'boss_jobs_final.csv')
OUT = os.path.join(base, 'boss_jobs_final_dedup.csv')

print("=" * 60)
print("=== BOSS JD 文本去重 ===")
print("=" * 60)

# 读取
with open(SRC, 'r', encoding='utf-8-sig', errors='replace') as f:
    r = csv.reader(f)
    header = next(r)
    rows = list(r)

total = len(rows)
print(f"\n原始: {total} 行")

jd_idx = header.index('jd_text')

# 去重：按 jd_text 内容（归一化：strip + 统一空白字符）
seen = set()
dedup_rows = []
dup_count = 0
empty_count = 0

for row in rows:
    jd_text = row[jd_idx].strip() if len(row) > jd_idx and row[jd_idx] else ''
    
    # 空/极短JD单独统计，但仍保留（不同ID的空JD不重复）
    if not jd_text or len(jd_text) <= 50:
        # 空JD：只保留 ID 唯一的，否则按 ID 去重会有0个重复
        # 但为了完整性，空JD全部保留（无内容可去重）
        dedup_rows.append(row)
        empty_count += 1
        continue
    
    # 归一化：替换连续空白为单个空格
    norm = ' '.join(jd_text.split())
    if len(norm) > 200:
        # 长JD用前200字符+后50字符做指纹（容忍微小差异）
        fingerprint = norm[:200] + '|||' + norm[-50:]
    else:
        fingerprint = norm
    
    if fingerprint in seen:
        dup_count += 1
    else:
        seen.add(fingerprint)
        dedup_rows.append(row)

print(f"空/短JD(保留全部): {empty_count}")
print(f"重复JD(剔除): {dup_count}")
print(f"去重后: {len(dedup_rows)} 行")

# 写出
with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(header)
    for row in dedup_rows:
        w.writerow(row)

sz = os.path.getsize(OUT)
print(f"\n输出: {OUT}")
print(f"大小: {sz/1024/1024:.1f}MB")

# 验证
print(f"\n=== 验证去重后 ===")
ids = [r[0].strip() for r in dedup_rows]
print(f"ID唯一: {len(ids)} == {len(set(ids))}")

jds = []
for r in dedup_rows:
    t = r[jd_idx].strip() if len(r) > jd_idx else ''
    if t and len(t) > 50:
        jds.append(' '.join(t.split()))
print(f"有效JD: {len(jds)}")
print(f"有效JD去重后: {len(set(jds))}")
print(f"JD文本有重复: {'是' if len(jds) != len(set(jds)) else '否'}")

print(f"\n=== 去重完成 ===")