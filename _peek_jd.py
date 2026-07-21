"""快速窥视 jd_text 内容"""
import sqlite3

DB = r'D:\hiring_data\boss_api\boss_jobs.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("SELECT COUNT(*), AVG(jd_len) FROM jobs WHERE jd_text IS NOT NULL AND jd_text != ''")
r = cur.fetchone()
print(f"有JD文本的行数: {r[0]:,}")
print(f"平均JD长度: {r[1]:.0f} 字符\n")

cur.execute("SELECT jd_text FROM jobs WHERE jd_text IS NOT NULL AND jd_text != '' LIMIT 3")
for i, row in enumerate(cur.fetchall()):
    print(f"=== SAMPLE {i+1} ===")
    print(row[0][:400])
    print()

conn.close()