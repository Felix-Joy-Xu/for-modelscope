"""以 boss_jobs_cleaned.csv (73,676行) 为基准，用 jsonl 更新 jd_text，输出完整 7.3w CSV"""
import os, json, csv

base = r'D:\hiring_data\boss_api'
CP = os.path.join(base, 'boss_jobs_cleaned.csv')
JL = os.path.join(base, 'boss_jd_full.jsonl')
OUT = os.path.join(base, 'boss_jobs_final.csv')

print("=" * 60)
print("=== 基于 7.3w cleaned.csv 合并 ===")
print("=" * 60)

# 1. 读取 cleaned.csv（7.3w 基准）
print("\n[1/3] 读取 cleaned.csv...")
with open(CP, 'r', encoding='utf-8', errors='replace') as f:
    r = csv.reader(f)
    header = next(r)
    header[0] = header[0].replace('\ufeff', '')  # 移除 BOM
    rows = []
    for line_num, row in enumerate(r, 1):
        if len(row) >= len(header):
            rows.append(row)
print(f"  读取: {len(rows)} 行, {len(header)} 列")
print(f"  列: {header}")

jd_idx = header.index('jd_text') if 'jd_text' in header else -1
jd_len_idx = header.index('jd_len') if 'jd_len' in header else -1

# 统计当前状态
before_filled = sum(1 for r in rows if jd_idx >= 0 and r[jd_idx] and len(r[jd_idx]) > 50)
print(f"  当前 jd_text 有效: {before_filled}/{len(rows)} ({before_filled/len(rows)*100:.1f}%)")

# 2. 从 jsonl 加载最新 jd_text
print("\n[2/3] 从 jsonl 加载最新 jd_text...")
jl_data = {}
dup_count = 0
with open(JL, 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            jid = d.get('encryptJobId', '').strip()
            if not jid:
                continue
            txt = d.get('jd_text', '')
            # 已存在的会被覆盖（保留最后一条=最新）
            if jid in jl_data:
                dup_count += 1
            jl_data[jid] = txt if txt else ''
        except:
            pass
print(f"  jsonl 有效记录: {len(jl_data)} (重复 {dup_count} 条)")

# 3. 更新并写出
print(f"\n[3/3] 更新 jd_text 并写出 → {OUT}...")
updated = 0
new_filled = 0
skipped_no_match = 0

outrows = []
for row in rows:
    jid = row[0].strip()
    new_row = list(row)
    
    # 确保行长度足够
    while len(new_row) < len(header):
        new_row.append('')
    
    if jid in jl_data:
        new_jd = jl_data[jid]
        if new_jd and len(new_jd) > 50:
            if jd_idx >= 0:
                new_row[jd_idx] = new_jd
            if jd_len_idx >= 0:
                new_row[jd_len_idx] = str(len(new_jd))
            updated += 1
            new_filled += 1
        elif new_jd:
            # 不足50字的也更新
            if jd_idx >= 0:
                new_row[jd_idx] = new_jd
            updated += 1
    else:
        skipped_no_match += 1
        # 保留原有 jd_text
        if jd_idx >= 0 and row[jd_idx] and len(row[jd_idx]) > 50:
            new_filled += 1
    
    outrows.append(new_row)

# 写出
with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(header)
    for row in outrows:
        w.writerow(row)

print(f"  jsonl 匹配更新: {updated} 条")
print(f"  未匹配(保留原值): {skipped_no_match} 条")
print(f"  最终 jd_text 有效: {new_filled}/{len(outrows)} ({new_filled/len(outrows)*100:.1f}%)")

sz = os.path.getsize(OUT)
print(f"  文件大小: {sz/1024/1024:.1f}MB")
print(f"\n=== 合并完成 ===")