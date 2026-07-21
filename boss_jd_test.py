"""Boss直聘 JD测试抓取 - 从已有7.3万条数据中取100条ID抓取完整JD并导出CSV"""
import json
import csv
import time
import random
import ctypes
from pathlib import Path
from DrissionPage import ChromiumPage

# 配置
SOURCE_PATH = Path(r"D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl")
JD_PATH = Path(r"D:\hiring_data\boss_api\boss_jd_test.jsonl")
CSV_PATH = Path(r"D:\hiring_data\boss_api\boss_full_test.csv")
SAMPLE_SIZE = 100
JD_DELAY_MIN = 2.0
JD_DELAY_MAX = 5.0

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def load_sample_ids():
    """从已有数据加载前N个唯一ID"""
    ids = []
    with open(SOURCE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                ids.append(data["encryptJobId"])
            except:
                pass
    unique = list(dict.fromkeys(ids))[:SAMPLE_SIZE]
    log(f"从 {len(ids)} 条数据中取前 {len(unique)} 个唯一ID")
    return unique

def main():
    log("=== Boss JD 测试抓取 (100条) ===")
    
    job_ids = load_sample_ids()
    
    page = ChromiumPage()
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(2)
    
    ctypes.windll.user32.MessageBoxW(
        0,
        f"即将抓取前 {SAMPLE_SIZE} 条JD详情。\n请确认浏览器已登录Boss直聘。\n点击确定开始。",
        "JD测试抓取", 0x00001000 | 0x00000040
    )
    log("开始抓取JD...")
    
    success = 0
    fail = 0
    
    with open(JD_PATH, "w", encoding="utf-8") as fout:
        for idx, jid in enumerate(job_ids, 1):
            log(f"[{idx}/{SAMPLE_SIZE}] {jid}")
            
            url = f"https://www.zhipin.com/job_detail/{jid}.html"
            page.get(url)
            time.sleep(random.uniform(JD_DELAY_MIN, JD_DELAY_MAX))
            
            jd_ele = page.ele('.job-sec-text', timeout=3)
            if jd_ele and jd_ele.text.strip():
                record = {
                    "encryptJobId": jid,
                    "jd_text": jd_ele.text.strip(),
                    "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
                }
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                fout.flush()
                success += 1
                log(f"  ✓ {len(record['jd_text'])} 字符")
            else:
                fail += 1
                log(f"  ✗ 无JD内容，可能岗位已下线")
    
    log(f"\nJD抓取完成: 成功 {success}, 失败 {fail}")
    
    # 合并导出CSV
    log("导出CSV...")
    jd_map = {}
    with open(JD_PATH, "r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            jd_map[d["encryptJobId"]] = d["jd_text"]
    
    headers = [
        "encryptJobId", "jobName", "salaryDesc", "brandName",
        "cityName", "areaDistrict", "businessDistrict",
        "jobDegree", "jobExperience", "skills", "jobLabels",
        "bossName", "bossTitle", "brandIndustry",
        "brandScaleName", "brandStageName", "jobTypeDesc",
        "jobDesc", "jd_text", "crawl_ts"
    ]
    
    count = 0
    with_jd = 0
    with open(SOURCE_PATH, "r", encoding="utf-8") as fin, \
         open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(headers)
        
        seen = set()
        for line in fin:
            data = json.loads(line)
            jid = data["encryptJobId"]
            if jid in seen or jid not in jd_map:
                continue
            seen.add(jid)
            
            skills = " | ".join(data.get("skills", []))
            labels = " | ".join(data.get("jobLabels", []))
            jd_text = jd_map.get(jid, "")
            if jd_text:
                with_jd += 1
            
            row = [
                jid,
                data.get("jobName", ""),
                data.get("salaryDesc", ""),
                data.get("brandName", ""),
                data.get("cityName", ""),
                data.get("areaDistrict", ""),
                data.get("businessDistrict", ""),
                data.get("jobDegree", ""),
                data.get("jobExperience", ""),
                skills,
                labels,
                data.get("bossName", ""),
                data.get("bossTitle", ""),
                data.get("brandIndustry", ""),
                data.get("brandScaleName", ""),
                data.get("brandStageName", ""),
                data.get("jobTypeDesc", ""),
                data.get("jobDesc", ""),
                jd_text,
                data.get("crawl_ts", ""),
            ]
            writer.writerow(row)
            count += 1
    
    log(f"CSV导出完成: {count} 条 (含JD: {with_jd} 条)")
    log(f"保存至: {CSV_PATH}")

if __name__ == "__main__":
    main()