"""Boss 直聘全量抓取 - 列表+完整JD 一站式方案

策略:
  第一阶段: 通过监听 API (joblist.json) 快速抓取职位列表
  第二阶段: 逐条访问详情页提取完整 JD 长文本

输出:
  - D:\hiring_data\boss_api\boss_list.jsonl   (列表数据含简短描述)
  - D:\hiring_data\boss_api\boss_full.csv      (最终CSV含完整JD)
"""

import json
import csv
import time
import random
import ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

# ═══════════════════ 配置 ═══════════════════
OUT_DIR = Path("D:/hiring_data/boss_api")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LIST_PATH = OUT_DIR / "boss_list.jsonl"
JD_PATH = OUT_DIR / "boss_jd_data.jsonl"
CSV_PATH = OUT_DIR / "boss_full.csv"

# 搜索配置
MAX_PAGES = 100               # 每个搜索维度翻页上限
API_TIMEOUT = 12              # API 响应等待(秒)
PAGE_DELAY = 2.5              # 翻页间隔防封
JD_DELAY_MIN = 2.0            # JD详情页抓取最小间隔
JD_DELAY_MAX = 5.0            # JD详情页抓取最大间隔

# 城市代码（可自行增删）
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
    "苏州": "101190400",
}

# 搜索关键词（可自行增删）
KEYWORDS = [
    "后端开发", "前端开发", "Java", "Python", "Go", "C++",
    "算法工程师", "AI", "大模型", "大数据", "测试开发", "全栈",
    "Android", "iOS", "架构师", "DevOps", "云计算",
    "安全工程师", "嵌入式", "游戏开发", "音视频",
    "深度学习", "自动驾驶", "NLP",
]

# 是否执行第二阶段JD抓取
FETCH_FULL_JD = True

# ═══════════════════ 工具函数 ═══════════════════

def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

def msg_box(title, text):
    """弹出Windows消息框"""
    ctypes.windll.user32.MessageBoxW(
        0, text, title,
        0x00001000 | 0x00000040  # MB_SYSTEMMODAL | MB_ICONINFORMATION
    )

# ═══════════════════ 第一阶段：列表抓取 ═══════════════════

def extract_list_fields(job):
    """从 API 返回的 job 对象提取字段"""
    return {
        "encryptJobId": job.get("encryptJobId", ""),
        "securityId": job.get("securityId", ""),
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
        "jobDesc": job.get("jobDesc", ""),          # API中的简短描述
        "crawl_ts": datetime.now(timezone.utc).isoformat(),
    }

def parse_joblist(resp):
    """解析 API 响应中的 jobList"""
    try:
        body = resp.response.body
        if isinstance(body, str):
            body = json.loads(body)
        return body.get("zpData", {}).get("jobList", [])
    except:
        return []

def scrape_list_for_query(page, url, label, existing_ids):
    """对单个搜索查询抓取列表"""
    records = []
    page_num = 0
    empty_count = 0

    page.get(url)
    time.sleep(3)

    while page_num < MAX_PAGES:
        page_num += 1
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
            record = extract_list_fields(job)
            jid = record["encryptJobId"]
            if jid in existing_ids:
                continue
            existing_ids.add(jid)
            records.append(record)
            new_count += 1

        log(f"  {label} 第{page_num}页: +{new_count} 条")
        time.sleep(PAGE_DELAY)

    return records

def phase1_list_scrape(page):
    """第一阶段：网格化列表抓取"""
    log("=" * 60)
    log("=== 第一阶段：网格化列表抓取 ===")

    existing_ids = set()
    if LIST_PATH.exists():
        with open(LIST_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    jid = json.loads(line).get("encryptJobId", "")
                    if jid:
                        existing_ids.add(jid)
                except:
                    pass
        log(f"断点恢复：已有 {len(existing_ids)} 条列表数据")

    total_grids = len(CITIES) * len(KEYWORDS)
    current = 0
    total_new = 0

    for city_name, city_code in CITIES.items():
        for kw in KEYWORDS:
            current += 1
            label = f"{city_name}-{kw}"
            log(f"\n[{current}/{total_grids}] 抓取: {label}")

            url = f"https://www.zhipin.com/web/geek/job?query={kw}&city={city_code}"
            recs = scrape_list_for_query(page, url, label, existing_ids)

            if recs:
                with open(LIST_PATH, "a", encoding="utf-8") as f:
                    for r in recs:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                total_new += len(recs)
                log(f"  >> {label} 贡献 {len(recs)} 条，累计新增 {total_new} 条")

    log(f"\n第一阶段完成！新增 {total_new} 条，去重总计 {len(existing_ids)} 条")
    return existing_ids

# ═══════════════════ 第二阶段：JD详情抓取 ═══════════════════

def collect_job_ids_from_list():
    """从列表数据中收集需要抓JD的job ID"""
    ids = []
    if not LIST_PATH.exists():
        log(f"列表文件 {LIST_PATH} 不存在！")
        return ids

    with open(LIST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                jid = data.get("encryptJobId")
                if jid:
                    ids.append(jid)
            except:
                pass

    unique_ids = list(dict.fromkeys(ids))
    log(f"从列表数据中收集到 {len(unique_ids)} 个唯一岗位ID")
    return unique_ids

def load_existing_jds():
    """加载已抓取JD的ID集合"""
    existing = set()
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing.add(json.loads(line)["encryptJobId"])
                except:
                    pass
    log(f"已有 {len(existing)} 条JD数据，将自动跳过")
    return existing

def scrape_single_jd(page, jid):
    """抓取单个岗位的完整JD"""
    url = f"https://www.zhipin.com/job_detail/{jid}.html"
    page.get(url)
    time.sleep(random.uniform(JD_DELAY_MIN, JD_DELAY_MAX))

    jd_ele = page.ele('.job-sec-text', timeout=3)
    if not jd_ele:
        log(f"  警告：找不到JD文本 (ID: {jid})")
        return ""

    return jd_ele.text

def phase2_jd_scrape(page):
    """第二阶段：抓取完整JD"""
    log("=" * 60)
    log("=== 第二阶段：JD详情抓取 ===")

    job_ids = collect_job_ids_from_list()
    if not job_ids:
        log("没有需要抓取的岗位ID，跳过第二阶段")
        return

    existing_jds = load_existing_jds()
    success = 0
    fail = 0
    total = len(job_ids)

    with open(JD_PATH, "a", encoding="utf-8") as fout:
        for idx, jid in enumerate(job_ids, 1):
            if jid in existing_jds:
                continue

            log(f"[{idx}/{total}] 抓取JD: {jid}")

            try:
                jd_text = scrape_single_jd(page, jid)
                if jd_text:
                    record = {
                        "encryptJobId": jid,
                        "jd_text": jd_text,
                        "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
                    }
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fout.flush()
                    success += 1
                    log(f"  ✓ 成功 ({len(jd_text)} 字符)")
                else:
                    fail += 1

            except Exception as e:
                log(f"  ✗ 异常: {e}")
                fail += 1
                time.sleep(5)

    log(f"\n第二阶段完成！成功: {success}，失败: {fail}")

# ═══════════════════ 第三阶段：合并导出CSV ═══════════════════

def phase3_export_csv():
    """合并列表数据与JD数据，导出为带完整JD的CSV"""
    log("=" * 60)
    log("=== 第三阶段：合并导出CSV ===")

    # 加载JD数据建立索引
    jd_map = {}
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    jd_map[data["encryptJobId"]] = data.get("jd_text", "")
                except:
                    pass
    log(f"加载了 {len(jd_map)} 条JD数据")

    if not LIST_PATH.exists():
        log(f"列表文件不存在: {LIST_PATH}")
        return

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
    with open(LIST_PATH, "r", encoding="utf-8") as fin, \
         open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fout:

        writer = csv.writer(fout)
        writer.writerow(headers)

        seen = set()
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                jid = data.get("encryptJobId", "")
                if jid in seen:
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
            except Exception as e:
                continue

    log(f"导出完成！共 {count} 条记录，其中 {with_jd} 条含完整JD")
    log(f"CSV保存至: {CSV_PATH}")

# ═══════════════════ 主流程 ═══════════════════

def main():
    log("╔══════════════════════════════════════════╗")
    log("║  Boss直聘全量抓取 - 含完整JD            ║")
    log("╚══════════════════════════════════════════╝")

    # 唤起浏览器
    page = ChromiumPage()
    page.listen.start('joblist.json')

    # 打开首页确认登录
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)

    msg_box(
        "Boss直聘全量抓取启动",
        "即将开始全量数据抓取。\n\n"
        "请确保浏览器中已登录 Boss 直聘。\n"
        "点击 [确定] 后脚本将自动运行。\n\n"
        f"抓取维度: {len(CITIES)} 城市 × {len(KEYWORDS)} 关键词\n"
        f"含完整JD: {'是' if FETCH_FULL_JD else '否'}"
    )
    log("用户确认登录，引擎启动！")

    # 第一阶段：列表抓取
    try:
        phase1_list_scrape(page)
    except Exception as e:
        log(f"第一阶段异常: {e}")

    if FETCH_FULL_JD:
        msg_box(
            "第二阶段确认",
            "第一阶段（列表抓取）已完成。\n\n"
            "即将开始第二阶段：逐条访问详情页提取完整JD。\n"
            "此阶段较慢，请耐心等待。\n\n"
            "点击 [确定] 继续。"
        )
        try:
            phase2_jd_scrape(page)
        except Exception as e:
            log(f"第二阶段异常: {e}")

    # 第三阶段：导出CSV
    try:
        phase3_export_csv()
    except Exception as e:
        log(f"导出CSV异常: {e}")

    log("\n" + "=" * 60)
    log("全流程完成！")
    log(f"列表数据: {LIST_PATH}")
    log(f"JD数据:   {JD_PATH}")
    log(f"最终CSV:  {CSV_PATH}")
    log("=" * 60)

if __name__ == "__main__":
    main()