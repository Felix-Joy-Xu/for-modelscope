"""BOSS直聘 JD全量抓取 V8 - CDP断连修复版
修复:
  1. 重启Edge后轮询CDP端口, 不等固定时间
  2. 级联失败熔断器: 连续N个导航失败→强制休眠
  3. 断连时在主循环层面重建page, 不依赖safe_navigate内部重连
"""

import json, csv, os, sys, time, random, subprocess, ctypes, socket
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
EDGE_PATH   = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
DEBUG_PORT  = 9222

GAP_MIN, GAP_MAX       = 0.8, 2.5
STAY_MIN, STAY_MAX     = 2.0, 4.0
RENDER_TIMEOUT         = 10
RETRY_BACKOFF          = 5
HOME_REFRESH           = 500

# V8新增: 熔断器配置
CIRCUIT_BREAKER_MAX = 30      # 连续失败N次触发熔断
CIRCUIT_BREAKER_COOL = 300    # 熔断冷却时间(秒)


# ==================== 工具函数 ====================
def ts():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{ts()}] {msg}", flush=True)

def js(page, code, default=None):
    """执行JS, 自动处理长文本序列化"""
    try:
        result = page.run_js(code)
        if result is None:
            return default
        # DrissionPage可能把JSON字符串自动解析了, 如果已经是str直接返回
        if isinstance(result, str):
            return result
        return default
    except:
        return default

def js_json(page, code, default=None):
    """执行JS并JSON.parse返回值 (JS侧用JSON.stringify包裹)"""
    try:
        raw = page.run_js(code)
        if raw is None:
            return default
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return raw if raw else default
        return str(raw) if raw else default
    except:
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


# ==================== CDP连接 (V8: 端口轮询) ====================
def is_cdp_ready(port=DEBUG_PORT, timeout=0.5):
    """检测CDP端口是否可连接"""
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.close()
        return True
    except:
        return False

def wait_cdp_ready(max_wait=30):
    """轮询等待CDP端口就绪, 返回True/False"""
    log("  ...等待CDP端口就绪...")
    waited = 0
    while waited < max_wait:
        if is_cdp_ready():
            log(f"  ✓ CDP端口就绪 ({waited}s)")
            return True
        time.sleep(1)
        waited += 1
    log(f"  ✗ CDP端口超时({waited}s)")
    return False

def launch_edge():
    """启动Edge调试模式（仅在CDP端口未就绪时才启动）"""
    if is_cdp_ready():
        log("  CDP端口已就绪, 跳过启动Edge")
        return
    user_data = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data")
    cmd = [EDGE_PATH, f"--remote-debugging-port={DEBUG_PORT}",
           f"--user-data-dir={user_data}", "--profile-directory=Default",
           "--no-first-run", "--no-default-browser-check",
           "--disable-blink-features=AutomationControlled"]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def kill_edge():
    subprocess.run("taskkill /F /IM msedge.exe 2>nul", shell=True, capture_output=True)
    time.sleep(2)

def check_login(page):
    """检测是否已登录BOSS直聘，未登录时弹窗提示"""
    try:
        # 先确保页面是在 zhipin.com 域名下，如果不是，先去首页
        cur_url = page.url or ""
        if "zhipin.com" not in cur_url:
            page.get("https://www.zhipin.com/web/geek/jobs?city=101010100")
            time.sleep(3)
        
        # 检查是否包含"登录"或"注册"按钮
        body = js(page, "return document.body ? document.body.innerText : ''", "")
        # 如果能在页面上找到特定的登录态标志，说明登录成功
        login_ok = js(page, """
            return !!(document.querySelector('.nav-figure') ||
                      document.querySelector('.user-figure') ||
                      document.querySelector('[ka=\"header-my\"]') ||
                      document.querySelector('.header-user-avatar') ||
                      document.querySelector('.user-avatar'));
        """, False)
        if login_ok:
            return True
        
        # 如果包含"登录/注册"或类似字样且没有登录标志，返回False
        if "登录/注册" in body or "用户登录" in body or ("登录" in body and "注册" in body and len(body) < 3000):
            return False
            
        return True # 默认乐观假设已登录
    except:
        return True  # 无法判断时乐观假设已登录

def connect_edge():
    """连接Edge CDP，用DrissionPage原生new_tab()打开BOSS页面"""
    BOSS_URL = "https://www.zhipin.com/web/geek/job?city=101010100"
    try:
        co = ChromiumOptions()
        co.set_local_port(DEBUG_PORT)
        co.set_browser_path(EDGE_PATH)
        browser = ChromiumPage(co)

        # ① 先查DrissionPage看到的标签页里是否有BOSS
        page = None
        try:
            tabs = browser.get_tabs()
            log(f"  DrissionPage找到 {len(tabs)} 个标签页:")
            for tab in tabs:
                try:
                    u = tab.url or ""
                    log(f"    {u[:70]}")
                    if "zhipin.com" in u:
                        page = tab
                        log(f"  ✓ 已有BOSS标签: {u[:60]}")
                        break
                except:
                    pass
        except Exception as e:
            log(f"  获取标签页失败: {e}")

        if page is None:
            # ② 没有BOSS标签 → 用DrissionPage自己的new_tab()创建
            # new_tab()是DrissionPage原生方法，不存在ID不同步问题
            log("  用DrissionPage新建标签页并导航BOSS...")
            try:
                page = browser.new_tab(BOSS_URL)
                log("  new_tab()成功")
                time.sleep(4)
            except Exception as e:
                log(f"  new_tab()失败: {e}, 尝试get_new_tab...")
                # 部分版本用不同的方法名
                try:
                    browser.new_tab()
                    time.sleep(1)
                    tabs = browser.get_tabs()
                    page = tabs[-1]  # 最新的标签
                    page.get(BOSS_URL)
                    time.sleep(4)
                except Exception as e2:
                    log(f"  备用方案也失败: {e2}")
                    page = browser

        # ③ 验证URL
        time.sleep(2)
        cur_url = ""
        try:
            cur_url = page.url or ""
        except:
            pass
        title = js(page, "return document.title || ''", "")
        log(f"✓ Edge连接成功, 标题: {title[:60]}")
        log(f"  当前URL: {cur_url[:80]}")

        # ④ 检测登录态，循环等待直到登录成功
        while not check_login(page):
            log("⚠️ 检测到未登录! 请在Edge中手动登录BOSS直聘后点击确定")
            ctypes.windll.user32.MessageBoxW(
                0,
                "检测到BOSS直聘未登录!\n\n请在Edge浏览器中手动登录账号\n登录完成后点击'确定'继续",
                "需要登录", 0x00001000 | 0x00000030
            )
            time.sleep(3)
            try:
                cur_url = page.url or ""
                if "zhipin.com" not in cur_url:
                    page.get(BOSS_URL)
                    time.sleep(3)
            except:
                pass
        log("  ✓ 登录状态正常，开始抓取")
        return page
    except Exception as e:
        log(f"✗ 连接Edge失败: {e}")
        return None

def reconnect_full():
    """完全重建Edge连接(杀进程→启动→轮询端口→连接)"""
    log("  ⚠ 开始完全重建Edge连接...")
    kill_edge()
    time.sleep(3)
    launch_edge()
    
    if not wait_cdp_ready(max_wait=30):
        return None
    
    # CDP就绪后额外等2秒让内部服务稳定
    time.sleep(2)
    return connect_edge()

def safe_navigate(page, url):
    """导航并验证URL是否真正到达目标页（防重定向）"""
    page.get(url)
    time.sleep(0.5)  # 等待可能的重定向完成
    return page


# ==================== 验证码检测 ====================
def check_captcha(page):
    """检测验证码, 返回(是否, 详情)"""
    try:
        body = js(page, "return document.body ? document.body.innerText : ''", "")
        if "系统检测到您的行为存在异常" in body or "请完成安全验证" in body:
            return True, "安全验证文字"
        if "安全验证" in body and "拖动" in body:
            return True, "滑块验证码"
    except:
        pass

    try:
        url_lower = page.url.lower()
        if "captcha" in url_lower or "verify" in url_lower or "security" in url_lower:
            return True, f"验证码URL: {page.url[:80]}"
    except:
        pass

    return False, ""

def handle_captcha(page):
    """弹出提示, 等待人工处理验证码"""
    log("=" * 50)
    log("⚠️⚠️⚠️ 检测到验证码! ⚠️⚠️⚠️")
    log("请在Edge中手动完成验证, 完成后回到这里...")
    log("=" * 50)
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "检测到验证码!\n\n请在Edge浏览器中完成人机验证后\n点击'确定'继续",
            "验证码暂停", 0x00001000 | 0x00000030
        )
    except:
        pass
    log("  验证已通过, 继续...")
    time.sleep(random.uniform(3, 5))


# ==================== JD提取 ====================
def extract_jd_from_text(page):
    """纯JS提取JD文本 - 优先用CSS选择器 (不用IIFE,避免DrissionPage双层function吞返回值)"""
    code = """
    var result = '';
    var sel = document.querySelector('.job-sec-text');
    if (sel) { var t = sel.innerText.trim(); if (t.length > 20) result = t; }
    if (!result) {
        sel = document.querySelector('.job-detail-section');
        if (sel) { var t = sel.innerText.trim(); if (t.length > 20) result = t; }
    }
    if (!result) {
        sel = document.querySelector('.job-detail');
        if (sel) { var t = sel.innerText.trim(); if (t.length > 20) result = t; }
    }
    if (!result) {
        var body = document.body ? document.body.innerText : '';
        var idx = body.indexOf('职位描述');
        if (idx < 0) idx = body.indexOf('岗位职责');
        if (idx < 0) idx = body.indexOf('任职要求');
        if (idx > -1) {
            var rest = body.substring(idx);
            var end = rest.search(/\\n公司介绍|\\n工商信息|\\n工作地址|\\nBOSS安全提示/);
            if (end > 0) rest = rest.substring(0, end);
            result = rest.trim();
        }
    }
    return JSON.stringify(result);
    """
    return js_json(page, code, "")

def wait_for_jd_render(page):
    """等待页面渲染 - 用CSS选择器直接检测"""
    waited = 0
    while waited < RENDER_TIMEOUT:
        # 优先用CSS选择器检测
        jd_el = js(page, """
            var sel = document.querySelector('.job-sec-text');
            return sel ? sel.innerText.length > 20 : false;
        """, False)
        if jd_el:
            return "ok"
        body_text = js(page, "return document.body ? document.body.innerText : ''", "")
        if "职位描述" in body_text or "岗位职责" in body_text or "任职要求" in body_text:
            return "ok"
        if "职位已过期" in body_text or "该职位已关闭" in body_text:
            return "expired"
        if "系统检测到您的行为存在异常" in body_text:
            return "captcha"
        time.sleep(0.5)
        waited += 0.5
    return "timeout"


# ==================== 反封禁辅助 ====================
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

def human_scroll(page):
    scroll_y = random.randint(100, 500)
    js(page, f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})")

def browse_list_page(page):
    """回列表页翻一翻"""
    try:
        page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    except:
        pass
    time.sleep(random.uniform(2, 4))
    for _ in range(random.randint(1, 3)):
        human_scroll(page)
    if random.random() < 0.3:
        try:
            x, y = random.randint(10, 100), random.randint(200, 400)
            js(page, f"""
                var el = document.elementFromPoint({x},{y});
                if(el) el.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true}}));
            """)
            time.sleep(random.uniform(0.5, 1.5))
        except:
            pass


# ==================== 主流程 ====================
def main():
    log("=" * 60)
    log("=== BOSS JD V8 CDP断连修复版 ===")
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

    # V8: 初始连接使用完整重建流程
    kill_edge()
    launch_edge()
    if not wait_cdp_ready():
        log("无法启动Edge CDP, 退出")
        return
    time.sleep(2)
    page = connect_edge()
    if page is None:
        log("初始连接Edge失败, 退出")
        return
    
    browse_list_page(page)

    ctypes.windll.user32.MessageBoxW(
        0,
        f"BOSS直聘 JD全量抓取 V8\n"
        f"CDP断连修复版\n\n"
        f"✅ 已完成: {len(done_ids)}\n"
        f"📋 待抓取: {len(pending)}\n"
        f"⏱ 预估: {len(pending)*9//3600} 小时\n\n"
        f"新增: 熔断器+端口轮询\n"
        f"请在Edge中点击'确定'开始",
        "BOSS JD V8", 0x00001000 | 0x00000040
    )

    success  = 0
    fail     = 0
    expired  = 0
    last_home = 0
    start_time = time.time()
    
    # V8: 熔断器状态
    consecutive_fails = 0

    log("开始抓取!\n")

    for idx, rec in enumerate(pending):
        jid = rec["encryptJobId"]

        # ======== V8: 熔断器检查 ========
        if consecutive_fails >= CIRCUIT_BREAKER_MAX:
            log(f"  🔥 熔断! 连续{consecutive_fails}次失败, 休眠{CIRCUIT_BREAKER_COOL}秒...")
            time.sleep(CIRCUIT_BREAKER_COOL)
            log("  休眠结束, 重建Edge连接...")
            new_page = reconnect_full()
            if new_page:
                page = new_page
                consecutive_fails = 0
                browse_list_page(page)
            else:
                log("  重建失败, 继续休眠60秒...")
                time.sleep(60)
                new_page = reconnect_full()
                if new_page:
                    page = new_page
                    consecutive_fails = 0
                else:
                    log("  连续重建失败, 退出")
                    break
            continue

        # ======== 验证码检查 ========
        is_captcha, detail = check_captcha(page)
        if is_captcha:
            handle_captcha(page)
            last_home = 0
            consecutive_fails = 0  # 人工介入, 重置熔断

        # ======== 随机间隔 ========
        gap = random.uniform(GAP_MIN, GAP_MAX)
        if random.random() < 0.08:
            gap += random.uniform(5, 12)
        time.sleep(gap)

        # ======== 导航 ========
        url = f"https://www.zhipin.com/job_detail/{jid}.html"
        nav_ok = False
        try:
            page = safe_navigate(page, url)
            # ★ 关键修复: 检测重定向 ★
            cur_url = ""
            try:
                cur_url = page.url or ""
            except:
                pass
            if cur_url and "job_detail" not in cur_url:
                # 被重定向了（落到首页/登录页）
                log(f"  ⚠ 重定向到: {cur_url[:80]} | {jid[:20]}...")
                # 判断是否触发了登录态失效
                if "login" in cur_url or "passport" in cur_url:
                    log("  检测到登录失效, 弹窗提示登录...")
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        "BOSS直聘登录态已失效!\n\n请在Edge浏览器中重新登录\n登录完成后点击'确定'继续",
                        "登录失效", 0x00001000 | 0x00000030
                    )
                    consecutive_fails = 0
                    # 重新导航
                    page = safe_navigate(page, url)
                    cur_url = page.url or ""
                if "job_detail" not in cur_url:
                    # 频率限制/反爬重定向，记为失败但不计入熔断
                    log(f"  ⚠ 反爬重定向, 等待30s冷却... | {jid[:20]}...")
                    time.sleep(30)
                    fail += 1
                    consecutive_fails += 1
                    save_jd(jid, "")
                    continue
            nav_ok = True
        except Exception as e:
            err = str(e)
            log(f"  ✗ 导航失败: {err[:80]} | {jid[:20]}...")
            
            # V8: 检测到断连 → 完整重建
            if "连接已断开" in err or "disconnected" in err.lower() or "连接" in err:
                log("  触发完整重建流程...")
                new_page = reconnect_full()
                if new_page:
                    page = new_page
                    consecutive_fails = 0
                    # 重建后再次尝试本job
                    try:
                        page = safe_navigate(page, url)
                        nav_ok = True
                        log("  重建后导航成功")
                    except:
                        log("  重建后仍导航失败, 跳过本job")
                else:
                    log("  重建失败")
            
            if not nav_ok:
                fail += 1
                consecutive_fails += 1
                save_jd(jid, "")
                continue
            else:
                consecutive_fails = 0

        # ======== 验证码检查(导航后) ========
        is_captcha, detail = check_captcha(page)
        if is_captcha:
            log(f"  ⚠ 检测到验证码: {detail}")
            handle_captcha(page)
            last_home = 0
            consecutive_fails = 0
            try:
                page = safe_navigate(page, url)
                time.sleep(3)
            except:
                fail += 1
                consecutive_fails += 1
                save_jd(jid, "")
                continue
            is_captcha, _ = check_captcha(page)
            if is_captcha:
                fail += 1
                consecutive_fails += 1
                save_jd(jid, "")
                continue

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
            status = wait_for_jd_render(page)
        except:
            status = "nav_error"

        if status == "captcha":
            handle_captcha(page)
            time.sleep(2)
            try:
                status = wait_for_jd_render(page)
            except:
                status = "nav_error"

        if status == "expired":
            save_jd(jid, "")
            expired += 1
            continue

        jd_text = ""
        try:
            jd_text = extract_jd_from_text(page)
        except:
            pass

        if jd_text and len(jd_text) > 50:
            save_jd(jid, jd_text)
            success += 1
            consecutive_fails = 0
            if (success + fail + expired) % 50 == 0:
                log(f"  ✓ {len(jd_text)}字 | 成功{success} 失败{fail} 过期{expired}")
        else:
            # 诊断: 前5次失败打印详细信息
            if fail < 5:
                cur_url = js(page, "return location.href || ''", "")
                body_preview = js(page, "return document.body ? document.body.innerText.substring(0,300) : ''", "")
                log(f"  [调试#{fail+1}] url={cur_url[:80]}")
                log(f"  [调试#{fail+1}] jd_text长度={len(jd_text) if jd_text else 0}")
                log(f"  [调试#{fail+1}] body前300字: {body_preview[:200]}")
                sel_test = js(page, """
                    var tests = {};
                    var s1 = document.querySelector('.job-sec-text');
                    tests['job-sec-text'] = s1 ? s1.innerText.substring(0,60) : null;
                    var s2 = document.querySelector('.job-detail-section');
                    tests['job-detail-section'] = s2 ? s2.innerText.substring(0,60) : null;
                    return JSON.stringify(tests);
                """, "{}")
                log(f"  [调试#{fail+1}] 选择器测试: {sel_test}")
            time.sleep(random.uniform(3, 6))
            try:
                human_scroll(page)
            except:
                pass
            time.sleep(2)
            try:
                jd_text = extract_jd_from_text(page)
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
                if (success + fail + expired) <= 10 or (success + fail + expired) % 50 == 0:
                    log(f"  - 无JD | 失败{fail} | {jid[:20]}...")

        total_done = success + fail + expired

        if (total_done - last_home) >= HOME_REFRESH:
            log(f"  [逛列表页...]")
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
                skills_v = [s.strip() for s in skills_v.split(",") if s.strip()]
            labels_v = data.get("jobLabels",[]) or data.get("welfareList",[])
            if isinstance(labels_v, str):
                labels_v = [l.strip() for l in labels_v.split(",") if l.strip()]
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