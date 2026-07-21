from IPython import utils
i"""BOSS直聘 JD全量抓取 V6 - 浏览器真人模拟(5天版)
- 浏览器直开详情页, 模拟鼠标+滚动+阅读
- 优化速度: ~7-9s/条 → 5-7天完成
- 反检测: 随机间隔、鼠标轨迹、不规律滚动
- 断点续抓 + 自动验证码处理
"""
import json
import time
import random
import os
import subprocess
from pathlib import Path
from DrissionPage import ChromiumPage, ChromiumOptions
import ctypes

# ==================== 配置 ====================
SOURCE_PATH = Path(r"D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl")
JD_PATH     = Path(r"D:\hiring_data\boss_api\boss_jd_full.jsonl")
CSV_PATH    = Path(r"D:\hiring_data\boss_api\boss_full_final.csv")

# 速度参数(5天目标: ~7s/条)
GAP_MIN     = 0.8      # 请求间隔最短
GAP_MAX     = 2.0      # 请求间隔最长
STAY_MIN    = 2.0      # 页面停留最短
STAY_MAX    = 4.0      # 页面停留最长
SCROLL_MIN  = 1        # 滚动次数最少
SCROLL_MAX  = 3        # 滚动次数最多

EDGE_PATH   = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT  = 9222

CAPTCHA_KEYWORDS = ["安全验证", "验证码", "人机验证", "滑块", "captcha", "verify",
                    "请完成安全验证", "拖动滑块", "请验证"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ==================== 数据加载 ====================

def collect_records():
    records = []; seen = set()
    with open(SOURCE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                d = json.loads(line)
                jid = d.get("encryptJobId","")
                if jid and jid not in seen:
                    seen.add(jid)
                    records.append({"encryptJobId": jid, "securityId": d.get("securityId","")})
            except: pass
    log(f"总记录: {len(records)}")
    return records


def load_done_ids():
    """只返回已有真JD的ID"""
    done = set()
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    jid = d.get("encryptJobId", "")
                    jd_text = d.get("jd_text", "")
                    if jid and len(jd_text) > 30:  # 有真JD才算完成
                        done.add(jid)
                except: pass
    log(f"已完成(含JD): {len(done)}")
    return done


def save_jd(jid, jd_text):
    record = {"encryptJobId": jid, "jd_text": jd_text,
              "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}
    with open(JD_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


# ==================== 浏览器连接 ====================

def connect_edge():
    log("连接Edge浏览器...")
    subprocess.run("taskkill /F /IM msedge.exe", shell=True, capture_output=True)
    time.sleep(3)

    user_data = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data")
    cmd = [EDGE_PATH, f"--remote-debugging-port={DEBUG_PORT}",
           f"--user-data-dir={user_data}", "--profile-directory=Default",
           "--no-first-run", "--no-default-browser-check",
           "--disable-blink-features=AutomationControlled"]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)

    for attempt in range(5):
        try:
            co = ChromiumOptions()
            co.set_local_port(DEBUG_PORT)
            co.set_browser_path(EDGE_PATH)
            w, h = random.randint(1200, 1600), random.randint(800, 1000)
            co.set_argument(f"--window-size={w},{h}")
            page = ChromiumPage(co)
            page.get("https://www.zhipin.com/web/geek/job?city=101010100")
            time.sleep(random.uniform(3, 5))
            title = page.title[:40]
            log(f"Edge: {title}")
            if any(kw in title for kw in CAPTCHA_KEYWORDS):
                log("⚠ 验证页面! 请手动完成验证后重新运行")
                ctypes.windll.user32.MessageBoxW(
                    0, "检测到Boss验证页面!\n请在Edge中手动完成验证后\n重新运行脚本。",
                    "验证提示", 0x00001000 | 0x00000030)
                raise RuntimeError("需要手动验证")
            return page
        except RuntimeError:
            raise
        except Exception as e:
            log(f"连接尝试 {attempt+1}/5: {e}")
            time.sleep(3)
    raise RuntimeError("无法连接Edge")


# ==================== 真人模拟 ====================

def human_mouse_move(page):
    """快速鼠标移动"""
    try:
        w = page.run_js("return window.innerWidth")
        h = page.run_js("return window.innerHeight")
        x = random.randint(100, w - 200)
        y = random.randint(200, h - 300)
        for step in range(random.randint(2, 4)):
            tx = x + random.randint(-40, 40)
            ty = y + random.randint(-20, 20)
            page.run_js(f"""
                var ev = new MouseEvent('mousemove', {{
                    clientX: {tx}, clientY: {ty},
                    bubbles: true, cancelable: true
                }});
                document.elementFromPoint({tx},{ty})?.dispatchEvent(ev);
            """)
            time.sleep(random.uniform(0.05, 0.2))
    except:
        pass


def human_scroll(page):
    """快速滚动模拟"""
    n = random.randint(SCROLL_MIN, SCROLL_MAX)
    for i in range(n):
        if random.random() < 0.5:
            human_mouse_move(page)
        dist = random.randint(100, 400)
        if random.random() < 0.15 and i > 0:
            dist = random.randint(-150, -30)  # 偶尔回滚
        page.run_js(f"window.scrollBy({{top: {dist}, behavior: 'smooth'}})")
        time.sleep(random.uniform(0.4, 1.0))


def check_captcha(page):
    """检测风控"""
    try:
        title = page.title.lower()
        body = page.ele("body").text.lower() if page.ele("body", timeout=1) else ""
        for kw in CAPTCHA_KEYWORDS:
            if kw in title or kw in body:
                return True, f"'{page.title[:30]}'"
        return False, ""
    except:
        return False, ""


def handle_captcha(page):
    """处理验证码"""
    log("\n" + "!" * 50)
    log("!!! 检测到验证码 !!!")
    log("!" * 50)
    ctypes.windll.user32.MessageBoxW(
        0, "Boss触发了验证码!\n\n请在Edge中手动完成验证,\n然后点确定继续。",
        "验证码!", 0x00001000 | 0x00000030)
    log("等待手动验证...")
    while True:
        time.sleep(5)
        is_captcha, detail = check_captcha(page)
        if not is_captcha:
            log("✓ 验证通过")
            rest = random.randint(120, 300)
            log(f"   休息 {rest//60} 分钟降风险...")
            time.sleep(rest)
            return
        log(f"   仍在验证... ({detail})")


def read_jd(page):
    """从详情页DOM读JD - 多策略提取"""
    # 策略1: 精确选择器
    selectors = [
        ".job-sec-text",
        ".job-detail-section .text",
        "#main .job-detail .text",
        ".detail-content",
        ".job-desc",
    ]
    for sel in selectors:
        ele = page.ele(sel, timeout=2)
        if ele:
            text = ele.text.strip()
            if text and len(text) > 50:
                return text
    
    # 策略2: innerText 全局提取, 定位"职位描述"后文本
    try:
        all_text = page.run_js("return document.body?.innerText || ''")
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]
        # 找到"职位描述"或"岗位职责"的起始行
        start_idx = None
        for i, line in enumerate(lines):
            if any(kw in line for kw in ["职位描述", "岗位职责", "任职要求", "岗位要求"]):
                start_idx = i
                break
        if start_idx is not None:
            # 收集接下来 ~2000 字的文本
            jd_lines = []
            total = 0
            for line in lines[start_idx:]:
                jd_lines.append(line)
                total += len(line)
                if total > 2000:
                    break
            text = "\n".join(jd_lines)
            if len(text) > 50:
                return text
    except:
        pass
    
    return ""


# ==================== 主流程 ====================

def main():
    log("=" * 60)
    log("=== BOSS JD V6 浏览器真人模拟 ===")
    log(f"   间隔: {GAP_MIN}-{GAP_MAX}s | 停留: {STAY_MIN}-{STAY_MAX}s")
    log(f"   滚动: {SCROLL_MIN}-{SCROLL_MAX}次 | 目标: 5天完成")
    log("=" * 60)

    all_records = collect_records()
    done_ids    = load_done_ids()
    pending = [r for r in all_records if r["encryptJobId"] not in done_ids]

    log(f"待抓取: {len(pending)} / 总: {len(all_records)}")

    if not pending:
        log("✅ 全部完成!")
        export_csv()
        return

    page = connect_edge()
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(random.uniform(2, 3))

    success = 0
    fail    = 0
    start_time = time.time()
    prev_done = len(done_ids)

    log(f"\n开始! 预计 {(len(pending)*7.5/3600):.1f}h 完成\n")

    for idx, rec in enumerate(pending):
        jid = rec["encryptJobId"]

        # 每50条打印进度
        if (success + fail) % 50 == 0 and (success + fail) > 0:
            elapsed = time.time() - start_time
            done_now = success + fail
            rate = done_now / max(elapsed, 1)
            eta = (len(pending) - done_now) / max(rate, 0.01)
            log(f"  [{done_now}/{len(pending)}] {100*done_now//len(pending)}% | "
                f"{rate:.2f}条/s | 成功:{success} 失败:{fail} | ETA:{eta/3600:.1f}h")

        # 请求间隔
        gap = random.uniform(GAP_MIN, GAP_MAX)
        # 8%概率长间隔(模拟离开工位)
        if random.random() < 0.08:
            gap += random.uniform(5, 12)
        time.sleep(gap)

        # 导航到详情页
        url = f"https://www.zhipin.com/job_detail/{jid}.html"
        try:
            page.get(url)
        except Exception as e:
            log(f"  ✗ 导航失败: {e}")
            fail += 1
            save_jd(jid, "")
            continue

        # 检查验证码
        is_captcha, detail = check_captcha(page)
        if is_captcha:
            log(f"  ⚠ 验证码: {detail}")
            handle_captcha(page)
            try:
                page.get(url)
                time.sleep(2)
            except:
                fail += 1
                save_jd(jid, "")
                continue
            is_captcha, _ = check_captcha(page)
            if is_captcha:
                fail += 1
                save_jd(jid, "")
                continue

        # 模拟真人行为
        human_mouse_move(page)
        time.sleep(random.uniform(0.3, 0.8))
        human_scroll(page)

        # 停留阅读
        stay = random.uniform(STAY_MIN, STAY_MAX)
        if random.random() < 0.1:
            stay += random.uniform(3, 8)
        time.sleep(stay)

        # 读取JD
        jd_text = read_jd(page)
        
        if jd_text and len(jd_text) > 50:
            save_jd(jid, jd_text)
            success += 1
        else:
            # 重试: 页面可能还在渲染, 多等+滚动+再等+再读
            time.sleep(random.uniform(3, 6))
            human_scroll(page)
            time.sleep(2)
            jd_text = read_jd(page)
            if jd_text and len(jd_text) > 50:
                save_jd(jid, jd_text)
                success += 1
            else:
                save_jd(jid, "")
                fail += 1
                if idx < 5:
                    log(f"  ⚠ JD为空: {jid[:20]}... (已重试)")

    # 完成
    elapsed = time.time() - start_time
    log(f"\n{'=' * 60}")
    log(f"✅ 完成! 耗时: {elapsed/3600:.1f}h")
    log(f"   成功: {success} | 失败: {fail}")
    log(f"   速率: {(success+fail)/elapsed:.2f}条/s")
    log(f"{'=' * 60}")
    export_csv()


def export_csv():
    log("导出CSV...")
    jd_map = {}
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                d = json.loads(line)
                jd_map[d["encryptJobId"]] = d.get("jd_text","")

    headers = [
        "encryptJobId","jobName","salaryDesc","brandName",
        "cityName","areaDistrict","businessDistrict",
        "jobDegree","jobExperience","skills","jobLabels",
        "bossName","bossTitle","brandIndustry",
        "brandScaleName","brandStageName","jobTypeDesc",
        "jobDesc","jd_text","crawl_ts"
    ]

    count = 0; with_jd = 0; seen = set()
    with open(SOURCE_PATH, "r", encoding="utf-8") as fin, \
         open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fout:
        import csv
        writer = csv.writer(fout)
        writer.writerow(headers)
        for line in fin:
            if not line.strip(): continue
            data = json.loads(line)
            jid = data.get("encryptJobId","")
            if jid in seen: continue
            seen.add(jid)
            jd_text = jd_map.get(jid,"")
            if jd_text: with_jd += 1
            row = [
                jid, data.get("jobName",""), data.get("salaryDesc",""),
                data.get("brandName",""), data.get("cityName",""),
                data.get("areaDistrict",""), data.get("businessDistrict",""),
                data.get("jobDegree",""), data.get("jobExperience",""),
                " | ".join(data.get("skills",[])),
                " | ".join(data.get("jobLabels",[])),
                data.get("bossName",""), data.get("bossTitle",""),
                data.get("brandIndustry",""), data.get("brandScaleName",""),
                data.get("brandStageName",""), data.get("jobTypeDesc",""),
                data.get("jobDesc",""), jd_text,
                data.get("crawl_ts",""),
            ]
            writer.writerow(row); count += 1

    log(f"CSV: {count}条, 含JD: {with_jd} ({100*with_jd//max(count,1)}%)")
    log(f"保存: {CSV_PATH}")


if __name__ == "__main__":
    main()