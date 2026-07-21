"""Boss 直聘 API 拦截版 - 监听网络请求获取结构化 JSON

核心思路 (来自 CSDN 博客):
  1. 访问搜索页 → scroll.to_bottom() 触发数据加载
  2. dp.listen.wait() 拦截 API 响应
  3. 解析 JSON: resp.response.body['zpData']['jobList']
  4. 每页 15 条职位，无需逐张点击卡片

相比 DOM 版:
  - 速度快 10x+（无需逐个点击卡片）
  - 数据完整（API 返回更多字段）
  - 稳定（不受 DOM 变化影响）

输出: D:\hiring_data\boss_api\tech_jobs_api.jsonl
"""
import json, time, ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

# ─────────────────── 配置 ───────────────────
OUT_DIR = Path("D:/hiring_data/boss_api")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "tech_jobs_api.jsonl"

CITY = "100010000"          # 全国
POSITION = "100000"         # 技术大类
MAX_PAGES = 300             # 最大页数
API_TIMEOUT = 15            # API 等待超时(秒)
PAGE_DELAY = 2.5           # 翻页间隔

# 兜底关键词
TECH_KW = [
    "后端开发", "前端开发", "Java", "Python", "Go", "C++",
    "算法工程师", "AI", "大数据", "测试开发", "全栈",
    "Android", "iOS", "架构师", "DevOps", "云计算",
    "安全工程师", "嵌入式", "游戏开发", "音视频",
    "深度学习", "自动驾驶", "NLP", "数据开发",
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
    """弹出对话框等待用户扫码登录"""
    page.get(f"https://www.zhipin.com/web/geek/job?city={CITY}")
    time.sleep(3)
    ctypes.windll.user32.MessageBoxW(
        0,
        "请在浏览器扫码登录 Boss 直聘\n\n登录完成后点击 [确定] 开始抓取",
        "BOSS直聘登录",
        0x00001000 | 0x00000040,
    )
    log("已确认登录")


def parse_joblist(resp):
    """解析 API 响应, 提取 jobList"""
    try:
        body = resp.response.body
        if isinstance(body, str):
            body = json.loads(body)
        joblist = body.get("zpData", {}).get("jobList", [])
        return joblist
    except Exception as e:
        log(f"  解析失败: {e}")
        return []


def scrape_with_url(page, url, label, existing_ids):
    """用 URL 访问并拦截 API 抓取, 返回记录列表"""
    records = []
    page_num = 0
    empty_count = 0

    log(f"[{label}] 访问: {url}")
    page.get(url)
    time.sleep(4)

    while page_num < MAX_PAGES:
        page_num += 1
        log(f"  [{label}] 第 {page_num} 页")

        # 滚动到底部触发数据加载
        try:
            page.scroll.to_bottom()
        except:
            pass

        # 等待 API 响应
        try:
            resp = page.listen.wait(timeout=API_TIMEOUT)
        except:
            empty_count += 1
            log(f"    API 超时 ×{empty_count}")
            if empty_count >= 3:
                break
            continue

        joblist = parse_joblist(resp)
        if not joblist:
            empty_count += 1
            log(f"    无数据 ×{empty_count}")
            if empty_count >= 3:
                break
            continue

        empty_count = 0
        new_count = 0
        for job in joblist:
            record = extract_fields(job)
            # 去重
            jid = record["encryptJobId"]
            if jid in existing_ids:
                continue
            existing_ids.add(jid)
            records.append(record)
            new_count += 1

        log(f"    API返回 {len(joblist)} 条, 新收录 {new_count} 条 (累计 {len(records)})")
        time.sleep(PAGE_DELAY)

    log(f"  [{label}] 完成, 共 {len(records)} 条")
    return records


def save_records(records):
    """追加写入 JSONL"""
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    log("=== Boss 直聘 API 拦截抓取 ===")

    # 加载已有数据 (断点续抓)
    existing_ids = set()
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    j = json.loads(line)
                    jid = j.get("encryptJobId", "")
                    if jid:
                        existing_ids.add(jid)
                except:
                    pass
        log(f"已有数据: {len(existing_ids)} 条 (断点续抓)")

    all_records = []

    # 启动浏览器
    log("启动浏览器...")
    page = ChromiumPage()
    
    # 核心：必须先开启监听，否则后面的 wait() 抓不到包！
    page.listen.start('joblist.json')
    
    wait_login(page)

    # ── 策略1: position=100000 技术大类 + scroll 触发 API ──
    log("\n" + "=" * 60)
    log("策略1: position=100000 技术分类 → 拦截 API")

    url1 = f"https://www.zhipin.com/web/geek/job?city={CITY}&position={POSITION}"
    recs1 = scrape_with_url(page, url1, "position-url", existing_ids)
    all_records.extend(recs1)
    save_records(recs1)

    if all_records:
        log(f"\n策略1 完成, 累计 {len(all_records)} 条")
        
    log("进入大批量关键词搜索模式")
    # ── 策略2: 关键词逐个搜索 ──
    log("\n" + "=" * 60)
    log("策略2: 关键词搜索 → 拦截 API")

    for i, kw in enumerate(TECH_KW, 1):
        log(f"\n--- [{i}/{len(TECH_KW)}] 关键词: {kw} ---")
        url2 = f"https://www.zhipin.com/web/geek/job?query={kw}&city={CITY}"
        recs2 = scrape_with_url(page, url2, kw, existing_ids)
        all_records.extend(recs2)
        save_records(recs2)
        log(f"  累计 {len(all_records)} 条")

    log(f"\n{'=' * 60}")
    log(f"抓取完成! 共 {len(all_records)} 条")
    log(f"输出: {OUT_PATH}")
    log(f"{'=' * 60}")
    log("浏览器保持打开, 手动关闭即可。")


if __name__ == "__main__":
    main()