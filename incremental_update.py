"""BOSS直聘增量更新 - 采集最新列表 + 去重 + 只抓新JD + 合并CSV"""
import json
import csv
import time
import random
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from collections import OrderedDict
import requests
from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 路径配置 ====================
OUT_DIR     = Path("D:/hiring_data/boss_api")
SOURCE_PATH = OUT_DIR / "tech_jobs_grid_72k.jsonl"   # 源列表(含旧+新)
JD_PATH     = OUT_DIR / "boss_jd_full.jsonl"          # JD数据
CSV_PATH    = OUT_DIR / "boss_jd_full.csv"            # 最终CSV
NEW_LIST_TMP= OUT_DIR / "new_listings_tmp.jsonl"      # 新采集列表暂存

API_URL     = "https://www.zhipin.com/wapi/zpgeek/job/detail.json"
EDGE_PATH   = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT  = 9222

# ==================== 搜索配置 ====================
MAX_PAGES = 30          # 每维度最大翻页(增量更新不用太多)
API_TIMEOUT = 12
PAGE_DELAY = 2.5
REQUEST_GAP = 0.5

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
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ==================== 步骤0: 加载已有ID ====================
def load_existing_ids():
    """从现有源列表加载所有已处理的encryptJobId"""
    ids = set()
    if SOURCE_PATH.exists():
        with open(SOURCE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    jid = json.loads(line).get("encryptJobId", "")
                    if jid: ids.add(jid)
                except: pass
    log(f"已有源列表: {len(ids)} 条")
    return ids

def load_done_jd_ids():
    """从JD文件加载已成功抓取JD的ID(非空)"""
    ids = set()
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    if d.get("jd_text", ""): ids.add(d["encryptJobId"])
                except: pass
    log(f"已有有效JD: {len(ids)} 条")
    return ids

# ==================== 步骤1: 采集最新列表 ====================
def extract_list_fields(job):
    return {
        "jobName": job.get("jobName", ""),
        "salaryDesc": job.get("salaryDesc", ""),
        "brandName": job.get("brandName", ""),
        "cityName": job.get("cityName", ""),
        "areaDistrict": job.get("areaDistrict", ""),
        "businessDistrict": job.get("businessDistrict", ""),
        "jobDegree": job.get("jobDegree", ""),
        "jobExperience": job.get("jobExperience", ""),
        "jobLabels": job.get("jobLabels", []),
        "skills": job.get("skills", []),
        "bossName": job.get("bossName", ""),
        "bossTitle": job.get("bossTitle", ""),
        "brandIndustry": job.get("brandIndustry", ""),
        "brandScaleName": job.get("brandScaleName", ""),
        "brandStageName": job.get("brandStageName", ""),
        "jobTypeDesc": job.get("jobTypeDesc", ""),
        "jobDesc": job.get("jobDesc", ""),
        "encryptJobId": job.get("encryptJobId", ""),
        "securityId": job.get("securityId", ""),
        "crawl_ts": datetime.now(timezone.utc).isoformat(),
    }

def parse_joblist(resp):
    try:
        body = resp.response.body
        if isinstance(body, str): body = json.loads(body)
        return body.get("zpData", {}).get("jobList", [])
    except: return []

def scrape_list_for_query(page, url, label, existing_ids):
    records = []; page_num = 0; empty_count = 0
    page.get(url); time.sleep(3)

    while page_num < MAX_PAGES:
        page_num += 1
        try: page.scroll.to_bottom()
        except: pass
        try:
            resp = page.listen.wait(timeout=API_TIMEOUT)
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
        log(f"  {label} 第{page_num}页: +{new_count} 条")
        time.sleep(PAGE_DELAY)
    return records

def phase1_collect_new():
    """采集最新列表，只保留新ID"""
    log("=" * 60)
    log("=== 阶段1: 采集最新职位列表 ===")
    existing_ids = load_existing_ids()

    all_new = []
    total_grids = len(CITIES) * len(KEYWORDS)
    current = 0

    page = ChromiumPage()
    page.listen.start('joblist.json')
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)

    log("请在浏览器中确认已登录BOSS直聘！30秒倒计时...")
    time.sleep(30)

    for city_name, city_code in CITIES.items():
        for kw in KEYWORDS:
            current += 1
            label = f"{city_name}-{kw}"
            log(f"\n[{current}/{total_grids}] 抓取: {label}")
            url = f"https://www.zhipin.com/web/geek/job?query={kw}&city={city_code}"
            recs = scrape_list_for_query(page, url, label, existing_ids)
            all_new.extend(recs)
            if all_new:
                with open(NEW_LIST_TMP, "w", encoding="utf-8") as f:
                    for r in all_new:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")

    log(f"\n阶段1完成！新增 {len(all_new)} 条，总计 {len(existing_ids)} 条")
    return all_new, page

# ==================== 步骤2: 用API抓取新JD ====================
def get_cookies_from_edge():
    subprocess.run("taskkill /F /IM msedge.exe 2>nul", shell=True, capture_output=True)
    time.sleep(2)
    user_data = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data")
    cmd = [EDGE_PATH, f"--remote-debugging-port={DEBUG_PORT}",
           f"--user-data-dir={user_data}", "--profile-directory=Default",
           "--no-first-run", "--no-default-browser-check"]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    co = ChromiumOptions()
    co.set_local_port(DEBUG_PORT)
    co.set_browser_path(EDGE_PATH)
    page = ChromiumPage(co)
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)
    cookies_dict = {}
    for c in page.cookies(): cookies_dict[c["name"]] = c["value"]
    ua = page.run_js("return navigator.userAgent")
    return cookies_dict, ua, page

def create_session(cookies_dict, ua):
    s = requests.Session()
    s.cookies.update(cookies_dict)
    s.headers.update({
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.zhipin.com/web/geek/job?city=101010100",
    })
    return s

def fetch_jd(session, jid, sid):
    for attempt in range(3):
        try:
            resp = session.get(API_URL,
                params={"jobId": jid, "securityId": sid}, timeout=15,
                headers={"Referer": f"https://www.zhipin.com/job_detail/{jid}.html"})
            if resp.status_code == 403:
                time.sleep(5 * (attempt + 1)); continue
            if resp.status_code != 200:
                time.sleep(2 * (attempt + 1)); continue
            data = resp.json()
            code = data.get("code")
            if code == 0 or code == "0":
                zp = data.get("zpData", {})
                jd_d = zp.get("jobDetail", {}) or zp.get("jobInfo", {})
                jd_text = jd_d.get("jobDesc", "") or jd_d.get("detailDescription", "")
                if not jd_text:
                    info = zp.get("jobInfo", {})
                    jd_text = info.get("jobDesc", "") or info.get("detailDescription", "")
                if jd_text: return jd_text
            if code in (-1, -2, -3, "-1", "-2", "-3"):  # 职位已下架
                return ""
            time.sleep(2); continue
        except: time.sleep(3)
    return ""

def phase2_fetch_new_jd(new_records):
    """只对新增的ID抓JD"""
    log("=" * 60)
    log(f"=== 阶段2: 抓取新JD ({len(new_records)}条) ===")
    if not new_records:
        log("无新记录，跳过")
        return 0

    done_ids = load_done_jd_ids()
    to_fetch = [(r["encryptJobId"], r["securityId"]) for r in new_records
                if r["encryptJobId"] not in done_ids]

    log(f"需要抓取: {len(to_fetch)} 条 (跳过已有JD: {len(new_records)-len(to_fetch)})")
    if not to_fetch:
        log("所有新记录已有JD，跳过")
        return 0

    cookies, ua, edge_page = get_cookies_from_edge()
    session = create_session(cookies, ua)

    success = 0; fail = 0
    with open(JD_PATH, "a", encoding="utf-8") as fout:
        for idx, (jid, sid) in enumerate(to_fetch, 1):
            jd_text = fetch_jd(session, jid, sid)
            if jd_text:
                rec = {"encryptJobId": jid, "jd_text": jd_text,
                       "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush(); success += 1
                log(f"  [{idx}/{len(to_fetch)}] + {jid[:20]}: {len(jd_text)}字")
            else:
                rec = {"encryptJobId": jid, "jd_text": "",
                       "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush(); fail += 1
                log(f"  [{idx}/{len(to_fetch)}] - {jid[:20]}: 空/已下架")

            time.sleep(REQUEST_GAP)
            if idx % 200 == 0:
                log(f"  进度: {idx}/{len(to_fetch)} | 成功{success} 失败{fail}")
                # 每200条刷新cookie
                cookies, ua, edge_page = get_cookies_from_edge()
                session = create_session(cookies, ua)

    log(f"\n阶段2完成！成功: {success}, 失败/空: {fail}")
    return success

# ==================== 步骤3: 合并&导出CSV ====================
def phase3_export_csv():
    log("=" * 60)
    log("=== 阶段3: 导出CSV ===")

    # 追加新列表到源文件
    if NEW_LIST_TMP.exists():
        new_count = 0
        with open(NEW_LIST_TMP, "r", encoding="utf-8") as fin:
            new_data = fin.read().strip()
        if new_data:
            with open(SOURCE_PATH, "a", encoding="utf-8") as fout:
                fout.write("\n" + new_data + "\n")
            for _ in new_data.strip().split("\n"):
                if _.strip(): new_count += 1
            log(f"新增列表已追加到源文件: +{new_count} 条")

    # 加载JD映射
    jd_map = {}
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    jd_map[d["encryptJobId"]] = d.get("jd_text", "")
                except: pass

    # 写入CSV
    seen = set(); count = 0; with_jd = 0
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "encryptJobId", "jobName", "salaryDesc", "brandName", "cityName",
            "areaDistrict", "businessDistrict", "jobDegree", "jobExperience",
            "skills", "jobLabels", "bossName", "bossTitle",
            "brandIndustry", "brandScaleName", "brandStageName",
            "jobTypeDesc", "jobDesc", "jd_text", "crawl_ts"
        ])

        with open(SOURCE_PATH, "r", encoding="utf-8") as fsrc:
            for line in fsrc:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                except: continue
                jid = d.get("encryptJobId", "")
                if jid in seen: continue
                seen.add(jid)
                jd_text = jd_map.get(jid, "")
                if jd_text: with_jd += 1

                def str_or(v, alt=""): return str(v) if v else alt
                skills_v = d.get("skills", []) or d.get("skillTags", [])
                if isinstance(skills_v, str):
                    skills_v = [s.strip() for s in skills_v.replace(","," ").split() if s.strip()]
                labels_v = d.get("jobLabels", []) or d.get("welfareList", [])
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

    log(f"CSV导出: {count}条, 含JD: {with_jd} ({100*with_jd//max(count,1)}%)")
    log(f"保存: {CSV_PATH}")
    return count

# ==================== 主流程 ====================
def main():
    log("╔══════════════════════════════════════════╗")
    log("║  BOSS直聘增量更新 - v1.0                 ║")
    log("╚══════════════════════════════════════════╝")
    log(f"搜索维度: {len(CITIES)}城市 × {len(KEYWORDS)}关键词")
    log(f"每维度最多翻页: {MAX_PAGES}")
    log("")

    # 阶段1: 采集最新列表
    new_records, list_page = phase1_collect_new()
    list_page.quit()

    if not new_records:
        log("\n== 无新增职位，跳过JD抓取 ==")
    else:
        log(f"\n新增 {len(new_records)} 个职位，即将开始抓取JD")
        input("按回车继续抓取JD...")
        # 阶段2: 抓取新JD
        phase2_fetch_new_jd(new_records)

    # 阶段3: 导出CSV
    phase3_export_csv()

    # 清理临时文件
    if NEW_LIST_TMP.exists(): NEW_LIST_TMP.unlink()

    log("\n全流程完成！")
    log(f"源列表: {SOURCE_PATH}")
    log(f"JD数据: {JD_PATH}")
    log(f"最终CSV: {CSV_PATH}")

if __name__ == "__main__":
    main()