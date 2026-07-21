"""Boss 直聘 - 网格化切割全量爬取 (降维打击终极形态)

策略: 10 大核心城市 × 24 个细分关键词 = 240 个搜索维度
每个维度提取上限 300 条 (平台物理极限)。
理论最大提取量: 72,000 条高质量横截面数据。

输出: D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl
"""
import json, time, ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

# ─────────────────── 配置 ───────────────────
OUT_DIR = Path("D:/hiring_data/boss_api")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "tech_jobs_grid_72k.jsonl"

MAX_PAGES = 300             # 翻页上限 (实际上Boss会在十几页后截断)
API_TIMEOUT = 12            # API 等待超时(秒)
PAGE_DELAY = 2.5           # 翻页间隔防封

# 核心十城 (一线 + 强二线互联网重镇)
CITIES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "西安": "101110100",
    "南京": "101190100",
    "苏州": "101190400"
}

# 程序员细分领域 (24个)
TECH_KW = [
    "后端开发", "前端开发", "Java", "Python", "Go", "C++",
    "算法工程师", "AI", "大模型", "大数据", "测试开发", "全栈",
    "Android", "iOS", "架构师", "DevOps", "云计算",
    "安全工程师", "嵌入式", "游戏开发", "音视频",
    "深度学习", "自动驾驶", "NLP"
]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def extract_fields(job):
    """从 API 返回的 job 对象中提取关键字段"""
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


def wait_login(page):
    page.get(f"https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)
    ctypes.windll.user32.MessageBoxW(
        0,
        "即将启动【网格化全量抓取】 (10城 × 24关键词 = 240个网格)\n\n"
        "请在浏览器扫码登录，完成滑块验证。\n"
        "点击 [确定] 后，脚本将自动运转数小时提取全部数据！",
        "启动全量网格化引擎",
        0x00001000 | 0x00000040,
    )
    log("已确认登录，网格化引擎启动！")


def parse_joblist(resp):
    try:
        body = resp.response.body
        if isinstance(body, str):
            body = json.loads(body)
        return body.get("zpData", {}).get("jobList", [])
    except:
        return []


def scrape_with_url(page, url, label, existing_ids):
    records = []
    page_num = 0
    empty_count = 0

    page.get(url)
    time.sleep(3)

    while page_num < MAX_PAGES:
        page_num += 1
        
        # 滚到底部触发加载
        try:
            page.scroll.to_bottom()
        except:
            pass

        try:
            resp = page.listen.wait(timeout=API_TIMEOUT)
        except:
            empty_count += 1
            if empty_count >= 2:
                break
            continue

        joblist = parse_joblist(resp)
        if not joblist:
            empty_count += 1
            if empty_count >= 2:
                break
            continue

        empty_count = 0
        new_count = 0
        for job in joblist:
            record = extract_fields(job)
            jid = record["encryptJobId"]
            if jid in existing_ids:
                continue
            existing_ids.add(jid)
            records.append(record)
            new_count += 1

        log(f"    {label} - 第{page_num}页: 收录 {new_count} 条")
        time.sleep(PAGE_DELAY)

    return records


def save_records(records):
    if not records:
        return
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    log("=== Boss 直聘 网格化全量爬取 ===")
    
    # 读入历史数据，断点续抓
    existing_ids = set()
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    jid = json.loads(line).get("encryptJobId", "")
                    if jid: existing_ids.add(jid)
                except:
                    pass
        log(f"加载断点进度，已有独立数据: {len(existing_ids)} 条")

    page = ChromiumPage()
    page.listen.start('joblist.json')
    wait_login(page)

    total_grabbed = 0
    total_grids = len(CITIES) * len(TECH_KW)
    current_grid = 0
    START_GRID = 118

    log("\n" + "=" * 60)
    for city_name, city_code in CITIES.items():
        for kw in TECH_KW:
            current_grid += 1
            if current_grid < START_GRID:
                continue
            
            label = f"{city_name}-{kw}"
            log(f"\n[{current_grid}/{total_grids}] 正在裂变抓取: {label}")
            
            url = f"https://www.zhipin.com/web/geek/job?query={kw}&city={city_code}"
            recs = scrape_with_url(page, url, label, existing_ids)
            
            save_records(recs)
            total_grabbed += len(recs)
            log(f"  [完成] {label} 贡献 {len(recs)} 条 (当前运行时已抓取: {total_grabbed} 条)")

    log(f"\n{'=' * 60}")
    log(f"终极抓取完成! 本次共斩获 {total_grabbed} 条独家数据")
    log(f"总计去重后规模: {len(existing_ids)} 条")
    log(f"全部保存于: {OUT_PATH}")
    log(f"{'=' * 60}")

if __name__ == "__main__":
    main()
