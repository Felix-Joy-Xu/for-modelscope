"""增量更新 - 断点续传版"""
import json, time, os, subprocess
from pathlib import Path
from datetime import datetime, timezone
from collections import OrderedDict
from DrissionPage import ChromiumPage

OUT_DIR     = Path("D:/hiring_data/boss_api")
SOURCE_PATH = OUT_DIR / "tech_jobs_grid_72k.jsonl"
JD_PATH     = OUT_DIR / "boss_jd_full.jsonl"
CSV_PATH    = OUT_DIR / "boss_jd_full.csv"
NEW_LIST_TMP= OUT_DIR / "new_listings_tmp.jsonl"
LOG_PATH    = OUT_DIR / "incremental_log.txt"

MAX_PAGES = 30
API_TIMEOUT = 12
PAGE_DELAY = 2.5

CITIES = OrderedDict({
    "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "杭州": "101210100", "成都": "101270100",
    "武汉": "101200100", "西安": "101110100", "南京": "101190100",
    "苏州": "101190400",
})

KEYWORDS = [
    "后端开发", "前端开发", "Java", "Python", "Go", "C++",
    "算法工程师", "AI", "大模型", "大数据", "测试开发", "全栈",
    "Android", "iOS", "架构师", "DevOps", "云计算",
    "安全工程师", "嵌入式", "游戏开发", "音视频",
    "深度学习", "自动驾驶", "NLP",
]

def log(msg):
    t = time.strftime('%H:%M:%S')
    print(f"[{t}] {msg}", flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{t}] {msg}\n")

def load_existing_ids():
    ids = set()
    for p in [SOURCE_PATH, NEW_LIST_TMP]:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        jid = json.loads(line).get("encryptJobId","")
                        if jid: ids.add(jid)
                    except: pass
    return ids

def load_done_grids():
    """从日志解析已完成的城市-关键词组合"""
    done = set()
    if LOG_PATH.exists():
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if "抓取:" in line:
                    label = line.split("抓取:")[-1].strip()
                    done.add(label)
    return done

def extract_list_fields(job):
    return {
        "jobName": job.get("jobName",""), "salaryDesc": job.get("salaryDesc",""),
        "brandName": job.get("brandName",""), "cityName": job.get("cityName",""),
        "areaDistrict": job.get("areaDistrict",""), "businessDistrict": job.get("businessDistrict",""),
        "jobDegree": job.get("jobDegree",""), "jobExperience": job.get("jobExperience",""),
        "jobLabels": job.get("jobLabels",[]), "skills": job.get("skills",[]),
        "bossName": job.get("bossName",""), "bossTitle": job.get("bossTitle",""),
        "brandIndustry": job.get("brandIndustry",""), "brandScaleName": job.get("brandScaleName",""),
        "brandStageName": job.get("brandStageName",""), "jobTypeDesc": job.get("jobTypeDesc",""),
        "jobDesc": job.get("jobDesc",""), "encryptJobId": job.get("encryptJobId",""),
        "securityId": job.get("securityId",""), "crawl_ts": datetime.now(timezone.utc).isoformat(),
    }

def parse_joblist(resp):
    try:
        body = resp.response.body
        if isinstance(body, str): body = json.loads(body)
        return body.get("zpData",{}).get("jobList",[])
    except: return []

def scrape_list_for_query(page, url, label, existing_ids):
    records = []; page_num = 0; empty_count = 0
    page.get(url); time.sleep(3)
    while page_num < MAX_PAGES:
        page_num += 1
        try: page.scroll.to_bottom()
        except: pass
        try: resp = page.listen.wait(timeout=API_TIMEOUT)
        except:
            empty_count += 1
            if empty_count >= 2: break
            continue
        joblist = parse_joblist(resp)
        if not joblist:
            empty_count += 1
            if empty_count >= 2: break
            continue
        empty_count = 0; new_count = 0
        for job in joblist:
            rec = extract_list_fields(job)
            jid = rec["encryptJobId"]
            if jid in existing_ids: continue
            existing_ids.add(jid); records.append(rec); new_count += 1
        log(f"  {label} 第{page_num}页: +{new_count}")
        time.sleep(PAGE_DELAY)
    return records

def main():
    log("=== 断点续传 ===")
    existing_ids = load_existing_ids()
    done_grids = load_done_grids()
    log(f"已有列表ID: {len(existing_ids)} 条")
    log(f"已完成网格: {len(done_grids)}")

    # 加载/创建临时数据
    existing_records = []
    if NEW_LIST_TMP.exists():
        with open(NEW_LIST_TMP, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try: existing_records.append(json.loads(line))
                except: pass
    log(f"已有临时数据: {len(existing_records)} 条")
    all_new = existing_records

    # 构建网格列表
    grids = []
    for city, code in CITIES.items():
        for kw in KEYWORDS:
            label = f"{city}-{kw}"
            grids.append((label, city, code, kw))
    total = len(grids)

    # 找到断点
    resume_idx = 0
    for i, (label,_,_,_) in enumerate(grids):
        if label not in done_grids:
            resume_idx = i
            break
    else:
        log("所有网格已完成!")
        return all_new

    log(f"断点: 从第 {resume_idx+1}/{total} 开始 (已完成 {resume_idx} 个)")

    page = ChromiumPage()
    page.listen.start('joblist.json')
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)
    log("确认已登录，5秒后继续...")
    time.sleep(5)

    for idx in range(resume_idx, total):
        label, city, code, kw = grids[idx]
        log(f"\n[{idx+1}/{total}] 抓取: {label}")
        url = f"https://www.zhipin.com/web/geek/job?query={kw}&city={code}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                recs = scrape_list_for_query(page, url, label, existing_ids)
                all_new.extend(recs)
                # 实时保存
                with open(NEW_LIST_TMP, "w", encoding="utf-8") as f:
                    for r in all_new:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                log(f"  >> {label}: +{len(recs)} 条, 累计 {len(all_new)} 条")
                break
            except Exception as e:
                log(f"  !! {label} 第{attempt+1}次失败: {e}")
                if attempt < max_retries - 1:
                    log(f"  重建浏览器连接...")
                    try: page.quit()
                    except: pass
                    time.sleep(5)
                    page = ChromiumPage()
                    page.listen.start('joblist.json')
                    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
                    time.sleep(3)
                else:
                    log(f"  !! {label} 最终失败，跳过")
                    with open(NEW_LIST_TMP, "w", encoding="utf-8") as f:
                        for r in all_new:
                            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        time.sleep(1)

    log(f"\n阶段1完成! 新增 {len(all_new)} 条")
    page.quit()
    return all_new

def load_done_jd_ids():
    ids = set()
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    if d.get("jd_text",""): ids.add(d["encryptJobId"])
                except: pass
    return ids

def export_csv():
    import csv
    log("=== 导出CSV ===")
    if NEW_LIST_TMP.exists():
        new_lines = []
        with open(NEW_LIST_TMP, "r", encoding="utf-8") as f:
            new_lines = [l.strip() for l in f if l.strip()]
        if new_lines:
            with open(SOURCE_PATH, "a", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")
            log(f"追加到源文件: {len(new_lines)} 条")

    jd_map = {}
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    jd_map[d["encryptJobId"]] = d.get("jd_text","")
                except: pass

    seen = set(); count = 0; with_jd = 0
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "encryptJobId","jobName","salaryDesc","brandName","cityName",
            "areaDistrict","businessDistrict","jobDegree","jobExperience",
            "skills","jobLabels","bossName","bossTitle",
            "brandIndustry","brandScaleName","brandStageName",
            "jobTypeDesc","jobDesc","jd_text","crawl_ts"
        ])
        with open(SOURCE_PATH, "r", encoding="utf-8") as fsrc:
            for line in fsrc:
                if not line.strip(): continue
                try: d = json.loads(line)
                except: continue
                jid = d.get("encryptJobId","")
                if jid in seen: continue
                seen.add(jid)
                jd_text = jd_map.get(jid,"")
                if jd_text: with_jd += 1

                def str_or(v, alt=""): return str(v) if v else alt
                skills_v = d.get("skills",[]) or d.get("skillTags",[])
                if isinstance(skills_v, str):
                    skills_v = [s.strip() for s in skills_v.replace(","," ").split() if s.strip()]
                labels_v = d.get("jobLabels",[]) or d.get("welfareList",[])
                if isinstance(labels_v, str):
                    labels_v = [l.strip() for l in labels_v.replace(","," ").split() if l.strip()]
                row = [
                    jid, str_or(d.get("jobName")), str_or(d.get("salaryDesc")),
                    str_or(d.get("brandName")), str_or(d.get("cityName")),
                    str_or(d.get("areaDistrict")), str_or(d.get("businessDistrict")),
                    str_or(d.get("jobDegree")), str_or(d.get("jobExperience")),
                    " | ".join(skills_v) if isinstance(skills_v, list) else str(skills_v),
                    " | ".join(labels_v) if isinstance(labels_v, list) else str(labels_v),
                    str_or(d.get("bossName")), str_or(d.get("bossTitle")),
                    str_or(d.get("brandIndustry")), str_or(d.get("brandScaleName")),
                    str_or(d.get("brandStageName")), str_or(d.get("jobTypeDesc")),
                    str_or(d.get("jobDesc")), jd_text,
                    str_or(d.get("crawl_ts")),
                ]
                writer.writerow(row); count += 1

    log(f"CSV: {count}条, 含JD: {with_jd} ({100*with_jd//max(count,1)}%)")
    log(f"保存: {CSV_PATH}")

if __name__ == "__main__":
    new_records = main()
    log(f"\n=== 阶段1结束: {len(new_records)} 条新列表 ===")
    log(f"新列表: {NEW_LIST_TMP}")
    export_csv()
    log("\n全流程完成!")
    log(f"源列表: {SOURCE_PATH}")
    log(f"JD数据: {JD_PATH}")
    log(f"最终CSV: {CSV_PATH}")
