"""窥视 skills 列的内容格式"""
import sqlite3

DB = r'D:\hiring_data\boss_api\boss_jobs.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("SELECT skills FROM jobs WHERE skills IS NOT NULL AND skills != '' LIMIT 30")
for row in cur.fetchall():
    s = row[0]
    # Show raw and length
    parts = s.split(',')
    print(f"len={len(s):4d}  fields={len(parts):2d}  [{s[:150]}{'...' if len(s)>150 else ''}]")

print("\n---")
cur.execute("SELECT COUNT(*) FROM jobs WHERE skills IS NOT NULL AND skills != ''")
print(f"有技能列的行数: {cur.fetchone()[0]:,}")

conn.close()