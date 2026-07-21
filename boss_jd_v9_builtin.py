"""BOSS直聘 JD全量抓取 V9 - DrissionPage内置浏览器版
相比V8:
  1. 使用DrissionPage内置浏览器管理(不手动启Edge CDP)
  2. JD提取函数极简化, 只用CSS选择器
  3. 熔断器30次
  4. 进度续抓
"""
import json, csv, os, sys, time, random, subprocess, ctypes
from pathlib import Path
from datetime import datetime

# 强制UTF-8输出，避免Windows GBK终端编码错误
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 配置 ====================
SOURCE_PATH = Path(r"D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl")
JD_PATH     = Path(r"D:\hiring_data\boss_api\boss_jd_full.jsonl")
CSV_PATH    = Path(r"D:\hiring_data\boss_api\boss_jd_full.csv")

GAP_MIN, GAP_MAX       = 2.5, 5.5
STAY_MIN, STAY_MAX     = 3.0, 6.0
RENDER_TIMEOUT         = 10
HOME_REFRESH           = 30
CIRCUIT_BREAKER_MAX    = 25
CIRCUIT_BREAKER_COOL   = 300


# ==================== 工具函数 ====================
def ts():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def js(page, code, default=None):
    try:
        result = page.run_js(code)
        if result is not None:
            return result
    except:
        pass
    return default

def save_jd(jid, jd_text):
    with open(JD_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "encryptJobId": jid,
            "jd_text": jd_text,
            "crawl_ts": datetime.now().isoformat()
        }, ensure_ascii=False) + "\n")


# ==================== 数据加载 ====================
def load_done_ids():
    done = set()
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    done.add(d["encryptJobId"])
                except:
                    pass
    return done

def collect_records():
    records = []
    seen = set()
    with open(SOURCE_PATH, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except:
                continue
            jid = row.get("encryptJobId", "").strip()
            if jid and jid not in seen:
                seen.add(jid)
                records.append(row)
    return records


# ==================== JD提取 (V9极简版) ====================
def extract_jd(page):
    """纯JS提取JD - 只用CSS选择器, 极简无bug"""
    # 方案A: 直接用 .job-sec-text
    jd = js(page, """
        var el = document.querySelector('.job-sec-text');
        if (!el) return '';
        var t = el.innerText || el.textContent || '';
        return t.trim();
    """, "")
    if jd and len(jd) > 30:
        return jd

    # 方案B: .job-detail-section
    jd = js(page, """
        var el = document.querySelector('.job-detail-section');
        if (!el) return '';
        var t = el.innerText || el.textContent || '';
        // 去掉 "微信扫码分享 举报 职位描述" 等前缀
        var idx = t.indexOf('职位描述');
        if (idx >= 0) t = t.substring(idx);
        return t.trim();
    """, "")
    if jd and len(jd) > 30:
        return jd

    # 方案C: body全文提取
    jd = js(page, """
        var body = document.body;
        if (!body) return '';
        var text = body.innerText || body.textContent || '';
        var start = text.indexOf('职位描述');
        if (start < 0) start = text.indexOf('岗位职责');
        if (start < 0) start = text.indexOf('任职要求');
        if (start < 0) return '';
        var rest = text.substring(start);
        // 找结束标记
        var ends = ['公司介绍', '工商信息', '工作地址', 'BOSS安全提示',
                     '竞争力分析', '公司基本信息', '微信扫码', '看过该职位'];
        var minEnd = rest.length;
        for (var i = 0; i < ends.length; i++) {
            var pos = rest.indexOf(ends[i]);
            if (pos > 0 && pos < minEnd) minEnd = pos;
        }
        return rest.substring(0, minEnd).trim();
    """, "")
    return jd if (jd and len(jd) > 20) else ""

def wait_for_jd(page):
    """等待JD渲染"""
    waited = 0
    while waited < RENDER_TIMEOUT:
        body = js(page, "return document.body ? document.body.innerText : ''", "")
        if not body:
            time.sleep(0.5); waited += 0.5
            continue
        if "职位描述" in body or "岗位职责" in body or "任职要求" in body:
            return "ok"
        if "职位已过期" in body or "该职位已关闭" in body:
            return "expired"
        if "系统检测到您的行为存在异常" in body:
            return "captcha"
        time.sleep(0.5)
        waited += 0.5
    return "timeout"


# ==================== 验证码处理 ====================
def check_captcha(page):
    try:
        body = js(page, "return document.body ? document.body.innerText : ''", "")
        if "系统检测到您的行为存在异常" in body:
            return True
        if "安全验证" in body and "拖动" in body:
            return True
    except:
        pass
    try:
        if "captcha" in page.url.lower() or "verify" in page.url.lower():
            return True
    except:
        pass
    return False

def handle_captcha(page):
    log("=" * 50)
    log("⚠️ 检测到验证码! 请在浏览器中手动完成验证...")
    log("=" * 50)
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "检测到验证码!\n\n请在浏览器中完成人机验证后\n点击'确定'继续",
            "验证码暂停", 0x00001000 | 0x00000030
        )
    except:
        pass
    log("  验证已通过, 继续...")
    time.sleep(random.uniform(3, 5))


# ==================== 反封禁辅助 ====================
def human_scroll(page):
    scroll_y = random.randint(100, 500)
    js(page, f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})")

def human_mouse_move(page):
    w = js(page, "return window.innerWidth", 1200)
    h = js(page, "return window.innerHeight", 800)
    x = random.randint(w//3, 2*w//3)
    y = random.randint(100, h//2)
    js(page, f"""
        var ev = new MouseEvent('mousemove', {{
            clientX: {x}, clientY: {y}, bubbles: true
        }});
        document.dispatchEvent(ev);
    """)

def browse_list_page(page):
    """回列表页逛逛"""
    try:
        page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    except:
        pass
    time.sleep(random.uniform(2, 4))
    for _ in range(random.randint(1, 3)):
        human_scroll(page)
        time.sleep(random.uniform(0.3, 1.0))


# ==================== 主流程 ====================
def main():
    log("=" * 60)
    log("=== BOSS JD V9 内置浏览器版 ===")
    log(f"   间隔: {GAP_MIN}-{GAP_MAX}s | 停留: {STAY_MIN}-{STAY_MAX}s")
    log(f"   熔断器: 连续{CIRCUIT_BREAKER_MAX}次失败后休眠{CIRCUIT_BREAKER_COOL}s")
    log("=" * 60)

    all_records = collect_records()
    done_ids    = load_done_ids()
    pending = [r for r in all_records if r["encryptJobId"] not in done_ids]

    log(f"去重后唯一ID: {len(all_records)}")
    log(f"已完成(有效JD): {len(done_ids)} 条")
    log(f"待抓取: {len(pending)} / 总: {len(all_records)}")
    log(f"进度: {100*len(done_ids)//max(len(all_records),1)}% ({len(done_ids)}/{len(all_records)})")

    if not pending:
        log("已全部完成!")
        export_csv()
        return

    # V9: 使用DrissionPage内置浏览器(自动管理Edge)
    log("正在启动内置浏览器...")
    co = ChromiumOptions()
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.auto_port()

    page = ChromiumPage(co)
    log("浏览器已启动")

    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)
    title = js(page, "return document.title || ''", "")
    log(f"首页标题: {title[:60]}")

    browse_list_page(page)

    ctypes.windll.user32.MessageBoxW(
        0,
        f"BOSS直聘 JD全量抓取 V9\n内置浏览器版\n\n"
        f"✅ 已完成: {len(done_ids)}\n"
        f"📋 待抓取: {len(pending)}\n"
        f"⏱ 预估: {len(pending)*9//3600} 小时\n\n"
        f"请在浏览器中点击'确定'开始",
        "BOSS JD V9", 0x00001000 | 0x00000040
    )

    success  = 0
    fail     = 0
    expired  = 0
    last_home = 0
    start_time = time.time()
    consecutive_fails = 0

    log("开始抓取!\n")

    for idx, rec in enumerate(pending):
        jid = rec["encryptJobId"]

        # ======== 模拟人类休息机制 ========
        total_done = success + fail + expired
        if total_done > 0:
            if total_done % 20 == 0:
                micro_sleep = random.uniform(35, 75)
                log(f"  [微休眠] 已连续抓取 {total_done} 个职位，休息 {micro_sleep:.1f} 秒...")
                time.sleep(micro_sleep)
                browse_list_page(page)
            elif total_done % 100 == 0:
                macro_sleep = random.uniform(300, 600)
                log(f"  [大休眠] 已连续抓取 {total_done} 个职位，休息 {macro_sleep/60:.1f} 分钟...")
                time.sleep(macro_sleep)
                browse_list_page(page)

        # ======== 熔断器 ========
        if consecutive_fails >= CIRCUIT_BREAKER_MAX:
            log(f"  🔥 熔断! 连续{consecutive_fails}次失败, 休眠{CIRCUIT_BREAKER_COOL}秒...")
            time.sleep(CIRCUIT_BREAKER_COOL)
            log("  休眠结束, 刷新列表页...")
            browse_list_page(page)
            consecutive_fails = 0

        # ======== 验证码 ========
        if check_captcha(page):
            handle_captcha(page)
            last_home = 0
            consecutive_fails = 0

        # ======== 随机间隔 ========
        gap = random.uniform(GAP_MIN, GAP_MAX)
        if random.random() < 0.08:
            gap += random.uniform(5, 12)
        time.sleep(gap)

        # ======== 导航 ========
        url = f"https://www.zhipin.com/job_detail/{jid}.html"
        nav_ok = False
        for retry in range(3):
            try:
                page.get(url)
                nav_ok = True
                break
            except Exception as e:
                err = str(e)
                log(f"  ✗ 导航异常(重试{retry+1}/3): {err[:60]}")
                if "连接已断开" in err or "disconnected" in err.lower():
                    # 重建page
                    try:
                        time.sleep(3)
                        co = ChromiumOptions()
                        co.set_argument("--no-first-run")
                        co.set_argument("--no-default-browser-check")
                        co.auto_port()
                        page = ChromiumPage(co)
                        page.get("https://www.zhipin.com/web/geek/job?city=101010100")
                        time.sleep(3)
                        log("  ✓ 浏览器已重建")
                    except Exception as e2:
                        log(f"  ✗ 重建失败: {e2}")
                time.sleep(2)
        if not nav_ok:
            fail += 1
            consecutive_fails += 1
            save_jd(jid, "")
            continue

        # ======== 验证码(导航后) ========
        if check_captcha(page):
            handle_captcha(page)
            last_home = 0
            consecutive_fails = 0
            try:
                page.get(url)
                time.sleep(3)
            except:
                pass

        # ======== 模拟真人行为 ========
        try:
            human_mouse_move(page)
        except:
            pass
        time.sleep(random.uniform(0.3, 1.0))
        try:
            human_scroll(page)
        except:
            pass

        stay = random.uniform(STAY_MIN, STAY_MAX)
        if random.random() < 0.05:
            stay += random.uniform(3, 8)
        time.sleep(stay)

        if random.random() < 0.25:
            try:
                js(page, f"window.scrollBy({{top: {random.randint(-300,-50)}, behavior: 'smooth'}})")
            except:
                pass
            time.sleep(random.uniform(0.5, 1.5))

        # ======== 读取JD ========
        try:
            status = wait_for_jd(page)
        except:
            status = "nav_error"

        if status == "captcha":
            handle_captcha(page)
            time.sleep(2)
            try:
                status = wait_for_jd(page)
            except:
                status = "nav_error"

        if status == "expired":
            save_jd(jid, "")
            expired += 1
            continue

        jd_text = ""
        try:
            jd_text = extract_jd(page)
        except:
            jd_text = ""

        if jd_text and len(jd_text) > 50:
            save_jd(jid, jd_text)
            success += 1
            consecutive_fails = 0
            if success % 50 == 0:
                log(f"  ✓ {len(jd_text)}字 | 成功{success} 失败{fail} 过期{expired}")
        else:
            # 二次尝试: 滚动后重试
            time.sleep(random.uniform(2, 4))
            try:
                human_scroll(page)
            except:
                pass
            time.sleep(1.5)
            try:
                jd_text = extract_jd(page)
            except:
                jd_text = ""
            if jd_text and len(jd_text) > 50:
                save_jd(jid, jd_text)
                success += 1
                consecutive_fails = 0
            else:
                save_jd(jid, "")
                fail += 1
                consecutive_fails += 1
                # 前5次失败打印调式信息
                if fail <= 5:
                    body = js(page, "return document.body ? document.body.innerText.substring(0,200) : ''", "")
                    url_now = js(page, "return location.href || ''", "")
                    log(f"  [调试#{fail}] url={url_now[:70]}")
                    log(f"  [调试#{fail}] 提取结果长度={len(jd_text) if jd_text else 0}")
                    log(f"  [调试#{fail}] body前200: {body[:150]}")
                elif fail % 50 == 0:
                    log(f"  - 无JD | 失败{fail} | {jid[:20]}...")

        total_done = success + fail + expired

        if (total_done - last_home) >= HOME_REFRESH:
            log("  [逛列表页...]")
            browse_list_page(page)
            last_home = total_done

        if total_done % 50 == 0 and total_done > 0:
            elapsed = time.time() - start_time
            rate = total_done / max(elapsed, 1)
            eta = (len(pending) - total_done) / max(rate, 0.01)
            log(f"  ── [{total_done}/{len(pending)}] {100*total_done//len(pending)}% "
                f"│ 速率:{rate:.2f}/s │ 成功:{success} 失败:{fail} 过期:{expired} "
                f"│ ETA:{eta/3600:.1f}h ──")

    # ======== 收尾 ========
    elapsed = time.time() - start_time
    log(f"\n{'='*60}")
    log(f"✅ 完成! 耗时: {elapsed/3600:.1f}h")
    log(f"   成功: {success} | 失败: {fail} | 过期: {expired}")
    try:
        log(f"   速率: {total_done/elapsed:.2f}条/s")
    except:
        pass
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
    with open(SOURCE_PATH, "r", encoding="utf-8", errors="replace") as fin, \
         open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(headers)
        for line in fin:
            line = line.strip()
            if not line: continue
            try:
                data = json.loads(line)
            except:
                continue
            jid = data.get("encryptJobId","")
            if jid in seen: continue
            seen.add(jid)
            jd_text = jd_map.get(jid,"")
            if jd_text: with_jd += 1
            def str_or(v, alt=""):
                return str(v) if v else alt
            skills_v = data.get("skills",[]) or data.get("skillTags",[])
            if isinstance(skills_v, str):
                skills_v = [s.strip() for s in skills_v.replace(","," ").split() if s.strip()]
            labels_v = data.get("jobLabels",[]) or data.get("welfareList",[])
            if isinstance(labels_v, str):
                labels_v = [l.strip() for l in labels_v.replace(","," ").split() if l.strip()]
            row = [
                jid, str_or(data.get("jobName")), str_or(data.get("salaryDesc")),
                str_or(data.get("brandName")), str_or(data.get("cityName")),
                str_or(data.get("areaDistrict")), str_or(data.get("businessDistrict")),
                str_or(data.get("jobDegree")), str_or(data.get("jobExperience")),
                " | ".join(skills_v) if isinstance(skills_v, list) else str(skills_v),
                " | ".join(labels_v) if isinstance(labels_v, list) else str(labels_v),
                str_or(data.get("bossName")), str_or(data.get("bossTitle")),
                str_or(data.get("brandIndustry")), str_or(data.get("brandScaleName")),
                str_or(data.get("brandStageName")), str_or(data.get("jobTypeDesc")),
                str_or(data.get("jobDesc")), jd_text,
                str_or(data.get("crawl_ts")),
            ]
            writer.writerow(row); count += 1

    log(f"CSV: {count}条, 含JD: {with_jd} ({100*with_jd//max(count,1)}%)")
    log(f"保存: {CSV_PATH}")


if __name__ == "__main__":
    main()