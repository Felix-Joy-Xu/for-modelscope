"""BOSS直聘 全量JD抓取 V4 - 高级反封禁版
- 随机鼠标移动模拟(先移后滚)
- 验证码/风控页面自动检测+暂停
- 不可预测的行为模式(有时快有时慢、有时回看)
- 阅读速度因人而异(随机3-15s)
- 定期"摸鱼"回列表页翻一翻
"""
import json
import csv
import time
import random
import os
import subprocess
from pathlib import Path
from DrissionPage import ChromiumPage, ChromiumOptions, Chromium
import ctypes

# ==================== 配置 ====================
SOURCE_PATH = Path(r"D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl")
JD_PATH     = Path(r"D:\hiring_data\boss_api\boss_jd_full.jsonl")
CSV_PATH    = Path(r"D:\hiring_data\boss_api\boss_full_final.csv")

# 反封禁参数(极速版 — 最少停留)
PAGE_STAY_MIN  = 2.0    # 阅读停留最短秒(等待渲染)
PAGE_STAY_MAX  = 4.0    # 阅读停留最长秒
BATCH_SIZE     = 2000   # 每2000条休息一次
BREAK_MIN_MIN  = 0.3    # 最少休息0.3分钟
BREAK_MAX_MIN  = 1.0    # 最多休息1.0分钟
HOME_REFRESH   = 600    # 每600条回列表页
MOUSE_MOVES    = 1      # 每页模拟鼠标移动次数
JD_WAIT_TIMEOUT = 8     # 等待JD渲染的超时秒数

EDGE_PATH   = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT  = 9222

# 验证码检测关键词
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
                data = json.loads(line)
                jid = data.get("encryptJobId",""); sid = data.get("securityId","")
                if jid and jid not in seen:
                    seen.add(jid)
                    records.append({"encryptJobId": jid, "securityId": sid})
            except: pass
    log(f"去重后唯一ID: {len(records)}")
    return records


def load_done_ids():
    """只跳过已有真实JD内容的ID（空JD不算完成，需重试）"""
    done = set()
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    jid = d.get("encryptJobId", "")
                    jd_text = d.get("jd_text", "")
                    if jid and len(jd_text) > 30:  # 只有真JD才算完成
                        done.add(jid)
                except: pass
    log(f"已完成(有效JD): {len(done)} 条")
    return done


def save_jd(jid, jd_text):
    record = {"encryptJobId": jid, "jd_text": jd_text,
              "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}
    with open(JD_PATH, "a", encoding="utf-8") as fout:
        fout.write(json.dumps(record, ensure_ascii=False) + "\n")
        fout.flush()


# ==================== 浏览器连接 ====================

def connect_edge():
    log("正在连接本地Edge浏览器(调试模式)...")
    subprocess.run("taskkill /F /IM msedge.exe", shell=True,
                   capture_output=True)
    time.sleep(3)

    user_data = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data")
    cmd = [EDGE_PATH, f"--remote-debugging-port={DEBUG_PORT}",
           f"--user-data-dir={user_data}", "--profile-directory=Default",
           "--no-first-run", "--no-default-browser-check",
           "--disable-blink-features=AutomationControlled"]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    log("Edge已启动(保留登录态)")

    for attempt in range(5):
        try:
            co = ChromiumOptions()
            co.set_local_port(DEBUG_PORT)
            co.set_browser_path(EDGE_PATH)
            # 随机窗口大小(模拟不同用户)
            w, h = random.randint(1200, 1600), random.randint(800, 1000)
            co.set_argument(f"--window-size={w},{h}")
            page = ChromiumPage(co)
            page.get("https://www.zhipin.com/web/geek/job?city=101010100")
            time.sleep(random.uniform(3, 5))
            title = page.title[:40]
            log(f"✓ Edge连接成功, 标题: {title}")
            if any(kw in title for kw in CAPTCHA_KEYWORDS):
                log("⚠ 检测到验证页面! 请手动完成验证后重新运行")
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

def safe_js(page, script, default=None):
    """安全执行JS, 页面刷新时返回default"""
    try:
        # 先确保页面就绪
        page.wait.doc_loaded(timeout=5)
        return page.run_js(script)
    except:
        return default


def human_mouse_move(page):
    """模拟鼠标随机移动(Boss会追踪鼠标轨迹)"""
    try:
        w = safe_js(page, "return window.innerWidth", 1200)
        h = safe_js(page, "return window.innerHeight", 800)
        x = random.randint(100, max(200, w - 200))
        y = random.randint(200, max(300, h - 300))
        for step in range(random.randint(2, 5)):
            tx = x + random.randint(-50, 50)
            ty = y + random.randint(-30, 30)
            safe_js(page, f"""
                var ev = new MouseEvent('mousemove', {{
                    clientX: {tx}, clientY: {ty},
                    bubbles: true, cancelable: true
                }});
                document.elementFromPoint({tx},{ty})?.dispatchEvent(ev);
            """)
            time.sleep(random.uniform(0.1, 0.4))
    except:
        pass


def human_scroll(page):
    """模拟真人浏览滚动(不规律、有回看) - 安全版"""
    try:
        safe_js(page, f"window.scrollBy({{top: {random.randint(150,500)}, "
                     f"behavior: 'smooth'}})")
    except:
        pass
    time.sleep(random.uniform(0.8, 2.0))
    try:
        safe_js(page, f"window.scrollBy({{top: {random.randint(400,900)}, "
                     f"behavior: 'smooth'}})")
    except:
        pass
    time.sleep(random.uniform(0.5, 1.5))
    # 有时回翻
    if random.random() < 0.3:
        try:
            safe_js(page, f"window.scrollBy({{top: {random.randint(-200,-50)}, "
                         f"behavior: 'smooth'}})")
        except:
            pass
        time.sleep(random.uniform(0.5, 1.0))


def check_captcha(page):
    """检测是否被风控 -- 用JS读取，避免触发page.title导致刷新"""
    try:
        title = page.run_js("return document.title || ''")[:80]
        body = page.run_js("return document.body?.innerText || ''").lower()[:2000]

        for kw in CAPTCHA_KEYWORDS:
            if kw in title.lower() or kw in body:
                return True, f"标题'{title[:30]}' 内容含'{kw}'"
        return False, ""
    except:
        return False, ""


def handle_captcha(page):
    """处理验证码: 暂停并弹窗通知"""
    log("\n" + "!" * 50)
    log("!!! 检测到验证码/风控 !!!")
    log("!" * 50)
    ctypes.windll.user32.MessageBoxW(
        0,
        "Boss直聘触发了验证码!\n\n请在Edge中手动完成验证,\n然后点击确定继续抓取。",
        "验证码!", 0x00001000 | 0x00000030
    )
    # 等待用户手动处理
    log("等待手动验证...")
    while True:
        time.sleep(5)
        is_captcha, detail = check_captcha(page)
        if not is_captcha:
            log("✓ 验证已通过, 继续抓取")
            # 验证通过后休息一下, 避免立刻被抓
            rest = random.randint(30, 60)
            log(f"   休息 {rest} 秒后再继续(降低再次触发概率)...")
            time.sleep(rest)
            return
        log(f"   仍在验证中... ({detail})")


# ==================== JD读取 ====================

def wait_for_jd_render(page, timeout=JD_WAIT_TIMEOUT):
    """等待JD详情页渲染完成（或检测到过期）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            # 快速检测：页面标题是否加载（用JS避免page.title触发刷新）
            title = page.run_js("return document.title || ''")
            if "安全验证" in title or "验证" in title:
                return "captcha"
            # 检测"已不存在"关键词 → 快速跳过
            body_text = safe_js(page, "return document.body?.innerText || ''", "")
            if any(kw in body_text for kw in ["该职位已不存在", "该职位已过期", "职位已关闭"]):
                return "expired"
            # 检测JD是否已渲染
            for sel in [".job-sec-text", ".job-detail-section .text"]:
                try:
                    ele = page.ele(sel, timeout=0.5)
                    if ele and len(ele.text.strip()) > 50:
                        return "ready"
                except:
                    pass
            # innerText 备选检测
            if any(kw in body_text for kw in ["职位描述", "岗位职责", "任职要求"]):
                return "ready"
        except:
            pass
        time.sleep(0.5)
    return "timeout"


def read_jd(page):
    """从详情页DOM读取JD文本 - 三策略（等待渲染+快速过期检测）"""
    # 先等待渲染
    status = wait_for_jd_render(page)
    if status in ("captcha", "expired"):
        return ""  # 验证码/过期 → 直接返回空（不浪费时间重试）

    try:
        # 策略1: CSS选择器提取
        selectors = [
            ".job-sec-text",
            ".job-detail-section .text",
            "#main .job-detail .text",
            ".detail-content",
            ".job-desc",
        ]
        for sel in selectors:
            try:
                ele = page.ele(sel, timeout=2)
                if ele:
                    text = ele.text.strip()
                    if text and len(text) > 50:
                        return text
            except:
                continue

        # 策略2: innerText全局提取, 定位"职位描述"后文本(兜底)
        all_text = safe_js(page, "return document.body?.innerText || ''", "")
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]
        start_idx = None
        for i, line in enumerate(lines):
            if any(kw in line for kw in ["职位描述", "岗位职责", "任职要求", "岗位要求"]):
                start_idx = i
                break
        if start_idx is not None:
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

        # 策略3: 从整个页面body文本中尝试提取含"任职"的长段落
        if len(all_text) > 200:
            paragraphs = [p.strip() for p in all_text.split("\n\n") if len(p.strip()) > 80]
            for p in paragraphs:
                if any(kw in p for kw in ["任职", "岗位", "职责", "要求", "经验"]):
                    return p
    except:
        pass

    return ""


# ==================== 反封禁辅助 ====================

def reconnect_page(page):
    """检测连接状态, 断开则重新连接(返回页面对)"""
    try:
        page.run_js("return document.title || ''")
        return page
    except:
        log("  ⚠ 连接断开, 正在重连...")
        time.sleep(3)
        for retry in range(5):
            try:
                co = ChromiumOptions()
                co.set_local_port(DEBUG_PORT)
                co.set_browser_path(EDGE_PATH)
                page = ChromiumPage(co)
                page.get("https://www.zhipin.com/web/geek/job?city=101010100")
                time.sleep(random.uniform(2, 3))
                log("  ✓ 重连成功")
                return page
            except Exception as e:
                log(f"  重连重试 {retry+1}/5: {e}")
                time.sleep(5)
        raise RuntimeError("重连失败")


def safe_navigate(page, url, max_retries=3):
    """带重连的安全导航"""
    for attempt in range(max_retries):
        try:
            page.get(url)
            return page
        except Exception as e:
            err = str(e)
            if "连接已断开" in err or "disconnected" in err.lower():
                log(f"  ⚠ 连接断开, 重连中 ({attempt+1}/{max_retries})...")
                page = reconnect_page(page)
                time.sleep(random.uniform(2, 4))
            else:
                raise
    raise Exception("导航失败(已重连)")


def browse_list_page(page):
    """回列表页翻一翻(模拟真人投简历时会浏览列表)"""
    try:
        page = safe_navigate(page, "https://www.zhipin.com/web/geek/job?city=101010100")
    except:
        pass
    try:
        # 回列表页翻一翻
        time.sleep(random.uniform(2, 4))
        # 模拟在列表页翻看
        for _ in range(random.randint(1, 3)):
            human_scroll(page)
        # 偶尔随机点一下列表项(但不真的打开)
        if random.random() < 0.3:
            item = page.ele(".job-card-wrap", timeout=2)
            if item:
                x = random.randint(10, 100)
                y = random.randint(10, 80)
                page.run_js(f"""
                    document.elementFromPoint({x},{y})?.dispatchEvent(
                        new MouseEvent('mouseover', {{bubbles: true}}));
                """)
                time.sleep(random.uniform(0.5, 1.5))
    except:
        pass


def long_break(page, batch_num, done_cnt, total):
    """长时间休息 -- 模拟下班吃饭/开会"""
    dur_min = random.uniform(BREAK_MIN_MIN, BREAK_MAX_MIN)
    dur_sec = int(dur_min * 60)
    log(f"\n{'='*55}")
    log(f"⏸ 第{batch_num}批完成 ({done_cnt}/{total}, {100*done_cnt//total}%)")
    log(f"   休息 {dur_min} 分钟...")
    log(f"   ⏰ 恢复: {time.strftime('%H:%M', time.localtime(time.time()+dur_sec))}")
    log(f"{'='*55}")

    # 回列表页待着
    browse_list_page(page)

    # 分段睡眠
    for elapsed in range(0, dur_sec, 30):
        time.sleep(min(30, dur_sec - elapsed))
        remaining = (dur_sec - elapsed) / 60
        if remaining > 1:
            log(f"   休息中... {remaining:.0f}分钟剩余")

    # 恢复后先逛逛列表页
    browse_list_page(page)


# ==================== 主流程 ====================

def main():
    log("=" * 60)
    log("=== BOSS JD 全量抓取 V4 - 高级反封禁版 ===")
    log(f"   停留: {PAGE_STAY_MIN}-{PAGE_STAY_MAX}s + 随机鼠标+滚动")
    log(f"   批次: {BATCH_SIZE}条 | 休息: {BREAK_MIN_MIN}-{BREAK_MAX_MIN}分钟")
    log(f"   每{HOME_REFRESH}条回列表页逛一逛")
    log("=" * 60)

    all_records = collect_records()
    done_ids     = load_done_ids()
    pending = [r for r in all_records if r["encryptJobId"] not in done_ids]

    log(f"待抓取: {len(pending)} / 总: {len(all_records)}")
    log(f"进度: {100*len(done_ids)//max(len(all_records),1)}%")

    if not pending:
        log("已全部完成!")
        export_csv()
        return

    page = connect_edge()
    browse_list_page(page)

    ctypes.windll.user32.MessageBoxW(
        0,
        f"BOSS直聘 JD全量抓取 V4\n"
        f"模式: 模拟真人阅读(鼠标+滚动+休息)\n\n"
        f"✅ 已完成: {len(done_ids)}\n"
        f"📋 待抓取: {len(pending)}\n"
        f"⏱ 预估: {len(pending)*13//3600} 小时\n\n"
        f"⚠ 如遇验证码会弹窗暂停\n"
        f"请在Edge中点击'确定'开始",
        "BOSS JD V4", 0x00001000 | 0x00000040
    )

    success     = len(done_ids)
    fail        = 0
    batch_cnt   = 0
    batch_num   = 1
    last_home   = 0

    log("开始抓取!\n")

    for idx, rec in enumerate(pending):
        jid = rec["encryptJobId"]

        # ======== 验证码检查(每次打开页面前) ========
        is_captcha, detail = check_captcha(page)
        if is_captcha:
            handle_captcha(page)
            # 验证通过后重置批次计数(相当于新开始)
            batch_cnt = 0
            last_home = 0

        # ======== 随机间隔(极速版) ========
        gap = random.uniform(0.8, 2.0) if random.random() < 0.85 \
              else random.uniform(2.5, 4.0)
        time.sleep(gap)

        # ======== 导航 ========
        real_done = success + fail
        log(f"[{idx+1}/{len(pending)}] {jid[:22]}... "
            f"(成功{success-len(done_ids)} 失败{fail})")

        url = f"https://www.zhipin.com/job_detail/{jid}.html"
        try:
            page = safe_navigate(page, url)
        except Exception as e:
            log(f"  ✗ 导航失败: {e}")
            fail += 1; batch_cnt += 1
            save_jd(jid, "")
            continue

        # ======== 验证码检查(打开后立即检查) ========
        is_captcha, detail = check_captcha(page)
        if is_captcha:
            log(f"  ⚠ 检测到验证码: {detail}")
            handle_captcha(page)
            batch_cnt = 0; last_home = 0
            # 重试当前这一条
            try:
                page = safe_navigate(page, url)
                time.sleep(3)
            except:
                fail += 1; batch_cnt += 1
                save_jd(jid, "")
                continue
            is_captcha, _ = check_captcha(page)
            if is_captcha:
                fail += 1; batch_cnt += 1
                save_jd(jid, "")
                continue

        # ======== 模拟真人行为 ========
        # 1. 鼠标随机移动(在阅读JD前)
        for _ in range(random.randint(1, MOUSE_MOVES)):
            human_mouse_move(page)
            time.sleep(random.uniform(0.3, 1.0))

        # 2. 模拟滚动阅读
        human_scroll(page)

        # 3. 停留(模拟阅读 -- 有人读得快有人读得慢)
        stay = random.uniform(PAGE_STAY_MIN, PAGE_STAY_MAX)
        # 5%概率读稍久
        if random.random() < 0.05:
            stay += random.uniform(3, 8)
        time.sleep(stay)

        # 4. 偶尔回翻
        if random.random() < 0.25:
            try:
                safe_js(page, f"window.scrollBy({{top: {random.randint(-300,-50)}, "
                             f"behavior: 'smooth'}})")
            except:
                pass
            time.sleep(random.uniform(0.5, 1.5))

        # ======== 读取JD ========
        jd_text = read_jd(page)

        if jd_text and len(jd_text) > 50:
            save_jd(jid, jd_text)
            success += 1
            log(f"  ✓ {len(jd_text)}字 (停留{stay:.0f}s) | 本批:{batch_cnt+1}")
        else:
            # 重试: 等几秒再读
            time.sleep(random.uniform(3, 6))
            human_scroll(page)
            time.sleep(2)
            jd_text = read_jd(page)
            if jd_text and len(jd_text) > 50:
                save_jd(jid, jd_text)
                success += 1
                log(f"  ✓ {len(jd_text)}字 (重试) | 本批:{batch_cnt+1}")
            else:
                save_jd(jid, "")
                fail += 1
                log(f"  - 无JD | 失败:{fail}")

        batch_cnt += 1

        # ======== 定期回列表页 ========
        if (idx + 1 - last_home) >= HOME_REFRESH:
            log(f"  [逛列表页...]")
            browse_list_page(page)
            last_home = idx + 1

        # ======== 批次休息 ========
        if batch_cnt >= BATCH_SIZE:
            long_break(page, batch_num, success + fail, len(all_records))
            batch_cnt = 0
            batch_num += 1
            last_home = 0

        # ======== 进度报告 ========
        total_cnt = success + fail
        if total_cnt % 50 == 0:
            pct = 100 * total_cnt // len(all_records)
            eta = (len(pending) - (total_cnt - len(done_ids))) * 13 / 3600
            log(f"  ── 总:{total_cnt}/{len(all_records)} ({pct}%) "
                f"│ 成功率:{100*success//total_cnt}% │ 预计:{eta:.0f}h ──")

    # ======== 收尾 ========
    log(f"\n{'='*60}")
    log(f"✅ 完成! 成功:{success} 失败:{fail} 总:{success+fail}")
    log(f"{'='*60}")
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