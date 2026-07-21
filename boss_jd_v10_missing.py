"""BOSS直聘 JD缺失补采 V10 - DrissionPage内置浏览器版
专门针对缺失的 10715 条记录进行补采。
"""
import json, csv, os, sys, time, random, subprocess, ctypes
from pathlib import Path
from datetime import datetime

# 强制UTF-8输出，避免Windows GBK终端编码错误
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 配置 ====================
SOURCE_PATH = Path(r"D:\hiring_data\boss_api\missing_jd_jobs.jsonl")
JD_PATH     = Path(r"D:\hiring_data\boss_api\boss_jd_full.jsonl")
CSV_PATH    = Path(r"D:\hiring_data\boss_api\boss_jobs_cleaned.csv")
DB_PATH     = Path(r"D:\hiring_data\boss_api\boss_jobs.db")

GAP_MIN, GAP_MAX       = 1.0, 2.5
STAY_MIN, STAY_MAX     = 1.5, 3.0
RENDER_TIMEOUT         = 8
HOME_REFRESH           = 50


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
    # 保存到 jsonl
    with open(JD_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "encryptJobId": jid,
            "jd_text": jd_text,
            "crawl_ts": datetime.now().isoformat()
        }, ensure_ascii=False) + "\n")
    
    # 实时更新到 sqlite 数据库
    if jd_text and len(jd_text) > 50:
        try:
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("UPDATE jobs SET jd_text = ? WHERE encryptJobId = ?", (jd_text, jid))
            conn.commit()
            conn.close()
        except Exception as e:
            log(f"  [DB更新失败] {e}")


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
                    # 只过滤成功抓取过的
                    if d.get("jd_text") and len(d.get("jd_text")) > 50:
                        done.add(d["encryptJobId"])
                except:
                    pass
    # 从数据库加载
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute("SELECT encryptJobId FROM jobs WHERE jd_text IS NOT NULL AND jd_text != ''")
        for row in cur.fetchall():
            done.add(row[0])
        conn.close()
    except:
        pass
    return done

def collect_records():
    records = []
    seen = set()
    if not SOURCE_PATH.exists():
        log(f"源文件 {SOURCE_PATH} 不存在！")
        return []
        
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
    jd = js(page, """
        var el = document.querySelector('.job-sec-text');
        if (!el) return '';
        var t = el.innerText || el.textContent || '';
        return t.trim();
    """, "")
    if jd and len(jd) > 30:
        return jd

    jd = js(page, """
        var el = document.querySelector('.job-detail-section');
        if (!el) return '';
        var t = el.innerText || el.textContent || '';
        var idx = t.indexOf('职位描述');
        if (idx >= 0) t = t.substring(idx);
        return t.trim();
    """, "")
    if jd and len(jd) > 30:
        return jd

    jd = js(page, """
        var body = document.body;
        if (!body) return '';
        var text = body.innerText || body.textContent || '';
        var start = text.indexOf('职位描述');
        if (start < 0) start = text.indexOf('岗位职责');
        if (start < 0) start = text.indexOf('任职要求');
        if (start < 0) return '';
        var rest = text.substring(start);
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
    """自动等待验证码消失，不弹窗阻塞"""
    log("⚠️ 检测到验证码，自动等待 60 秒...")
    for i in range(12):
        time.sleep(5)
        if not check_captcha(page):
            log(f"  ✓ 验证已通过（{i*5+5}s）")
            break
        if i % 4 == 3:
            log(f"  ... 仍在等待验证（{(i+1)*5}s）")
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

def record_failure(jid, reason):
    pass

def browse_list_page(page):
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
    log("=== BOSS JD 缺失补采 V10 ===")
    log("=" * 60)

    all_records = collect_records()
    if not all_records:
        return
        
    done_ids    = load_done_ids()
    pending = [r for r in all_records if r["encryptJobId"] not in done_ids]

    log(f"待补采列表中共有职位: {len(all_records)}")
    log(f"扣除已完成的, 实际需补采: {len(pending)}")

    if not pending:
        log("已全部补采完成!")
        return

    log("正在启动内置浏览器...")
    # 新用户数据目录 → 全新 Chrome 会话，旧号被封不影响新号
    NEW_USER_DATA = Path(r"D:\hiring_data\boss_api\chrome_user_data")
    NEW_USER_DATA.mkdir(parents=True, exist_ok=True)

    co = ChromiumOptions()
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument(f"--user-data-dir={NEW_USER_DATA}")
    co.set_argument("--profile-directory=Default")
    co.set_local_port(19333)  # 换端口，隔离旧会话

    page = ChromiumPage(co)
    log("浏览器已启动")

    # 无弹窗，直接用已登录的 Chrome 开始爬取
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)
    log("开始爬取...\n")

    log("=" * 50)
    log(f"📋 待抓取: {len(pending)}")
    log(f"⏱ 预估: {len(pending)*4//3600} 小时")
    log("=" * 50)

    success  = 0
    fail     = 0
    expired  = 0
    last_home = 0
    start_time = time.time()

    log("开始抓取!\n")

    for idx, rec in enumerate(pending):
        jid = rec["encryptJobId"]

        # ======== 模拟人类休息机制 ========
        total_done = success + fail + expired
        if total_done > 0:
            if total_done % 40 == 0:
                micro_sleep = random.uniform(10, 20)
                log(f"  [微休眠] 已连续抓取 {total_done} 个职位，休息 {micro_sleep:.1f} 秒...")
                time.sleep(micro_sleep)
                browse_list_page(page)
            elif total_done % 150 == 0:
                macro_sleep = random.uniform(60, 120)
                log(f"  [大休眠] 已连续抓取 {total_done} 个职位，休息 {macro_sleep/60:.1f} 分钟...")
                time.sleep(macro_sleep)
                browse_list_page(page)

        # ======== 验证码 ========
        if check_captcha(page):
            handle_captcha(page)
            last_home = 0

        gap = random.uniform(GAP_MIN, GAP_MAX)
        if random.random() < 0.08: gap += random.uniform(5, 12)
        time.sleep(gap)

        # ======== 导航 ========
        url = f"https://www.zhipin.com/job_detail/{jid}.html"
        nav_ok = False
        for retry in range(3):
            try:
                page.get(url, timeout=10)
                nav_ok = True
                break
            except Exception as e:
                err = str(e)
                log(f"  ✗ 导航异常(重试{retry+1}/3): {err[:60]}")
                if "连接已断开" in err or "disconnected" in err.lower() or "timeout" in err.lower() or "超时" in err:
                    try:
                        page.stop_loading()
                        if "已断开" in err or "disconnected" in err.lower():
                            time.sleep(2)
                            page = ChromiumPage()
                    except:
                        pass
                time.sleep(2)
        if not nav_ok:
            fail += 1
            continue

        if check_captcha(page):
            handle_captcha(page)
            last_home = 0
            try:
                page.get(url)
                time.sleep(3)
            except: pass
            
        # [优化]: 提前拦截 404 页面，避免在死链接上浪费 3-5 秒模拟人类操作的时间
        try:
            if "页面不存在" in str(page.title) or "404" in str(page.title):
                expired += 1
                record_failure(jid, "expired")
                # 加一个极短的微小休眠，防止请求过快被封
                time.sleep(random.uniform(0.3, 0.8))
                continue
        except Exception as e:
            pass

        try: human_mouse_move(page)
        except: pass
        time.sleep(random.uniform(0.3, 1.0))
        try: human_scroll(page)
        except: pass

        stay = random.uniform(STAY_MIN, STAY_MAX)
        if random.random() < 0.05: stay += random.uniform(3, 8)
        time.sleep(stay)

        if random.random() < 0.25:
            try: js(page, f"window.scrollBy({{top: {random.randint(-300,-50)}, behavior: 'smooth'}})")
            except: pass
            time.sleep(random.uniform(0.5, 1.5))

        try: status = wait_for_jd(page)
        except: status = "nav_error"

        if status == "captcha":
            handle_captcha(page)
            time.sleep(2)
            try: status = wait_for_jd(page)
            except: status = "nav_error"

        if status == "expired":
            expired += 1
            continue

        jd_text = ""
        try: jd_text = extract_jd(page)
        except: pass

        if jd_text and len(jd_text) > 50:
            save_jd(jid, jd_text)
            success += 1
            if success % 50 == 0:
                log(f"  ✓ {len(jd_text)}字 | 成功{success} 失败{fail} 过期{expired}")
        else:
            # 先用 title 快速判断是否"页面不存在"（此类页面会自动跳转，page.html 会崩溃）
            is_expired = False
            try:
                title = page.title or ""
                if "页面不存在" in title or "404" in title:
                    is_expired = True
            except:
                pass

            if not is_expired:
                # 二次重试提取 JD
                time.sleep(random.uniform(2, 4))
                try: human_scroll(page)
                except: pass
                time.sleep(1.5)
                try: jd_text = extract_jd(page)
                except: pass

            if jd_text and len(jd_text) > 50:
                save_jd(jid, jd_text)
                success += 1
                if success % 50 == 0:
                    log(f"  ✓ {len(jd_text)}字 | 成功{success} 失败{fail} 过期{expired}")
            elif is_expired:
                log(f"  - 职位过期(页面不存在) | {jid[:20]}...")
                expired += 1
            else:
                # 安全检查 page.html 判断是否下线
                try:
                    page_text = page.html or ""
                    if "该职位已关闭" in page_text or "职位已下线" in page_text:
                        log(f"  - 职位过期 | {jid[:20]}...")
                        expired += 1
                    else:
                        fail += 1
                        if fail % 50 == 0:
                            log(f"  - 无JD | 失败{fail} | {jid[:20]}...")
                except:
                    fail += 1
                    if fail % 50 == 0:
                        log(f"  - 无JD | 失败{fail} | {jid[:20]}...")

        total_done = success + fail + expired

        if (total_done - last_home) >= HOME_REFRESH:
            browse_list_page(page)
            last_home = total_done

        if total_done % 50 == 0 and total_done > 0:
            elapsed = time.time() - start_time
            rate = total_done / max(elapsed, 1)
            eta = (len(pending) - total_done) / max(rate, 0.01)
            log(f"  ── [{total_done}/{len(pending)}] {100*total_done//len(pending)}% "
                f"│ 速率:{rate:.2f}/s │ 成功:{success} 失败:{fail} 过期:{expired} "
                f"│ ETA:{eta/3600:.1f}h ──")

    elapsed = time.time() - start_time
    log(f"\n{'='*60}")
    log(f"✅ 补采完成! 耗时: {elapsed/3600:.1f}h")
    log(f"   成功: {success} | 失败: {fail} | 过期: {expired}")
    log(f"{'='*60}")

if __name__ == "__main__":
    main()
