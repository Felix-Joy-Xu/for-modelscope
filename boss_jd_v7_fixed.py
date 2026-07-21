"""BOSS直聘 JD全量抓取 V7 - 纯JS提取，不依赖CSS选择器
- 核心思路: 全部通过 page.run_js() 读取，永不使用 page.ele()
- 渲染检测: 等 innerText 出现 "职位描述/岗位职责" 或 body 达到足够长度
- JD提取: 从 innerText 中按行定位关键标记，截取候选区块
- 过期/不存在: 只看本页标题，不看 body 宽泛匹配
"""
import json
import csv
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

# 速度参数 (~8-10s/条, 约4-5天完成全量)
GAP_MIN       = 0.8      # 请求间隔最短
GAP_MAX       = 2.5      # 请求间隔最长
STAY_MIN      = 2.0      # 页面停留最短
STAY_MAX      = 4.0      # 页面停留最长
RENDER_TIMEOUT = 10      # 等待SPA渲染超时秒数
RETRY_BACKOFF  = 5       # 读不到JD后的重试等待秒数
HOME_REFRESH   = 500     # 每500条回列表页逛一逛

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
                jid = d.get("encryptJobId",""); sid = d.get("securityId","")
                if jid and jid not in seen:
                    seen.add(jid)
                    records.append({"encryptJobId": jid, "securityId": sid})
            except: pass
    log(f"去重后唯一ID: {len(records)}")
    return records


def load_done_ids():
    """只跳过已有真实JD内容的ID"""
    done = set()
    if JD_PATH.exists():
        with open(JD_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    d = json.loads(line)
                    jid = d.get("encryptJobId", "")
                    jd_text = d.get("jd_text", "")
                    if jid and len(jd_text) > 30:
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


# ==================== JS工具函数 ====================

def js(page, script, default=""):
    """执行JS, 异常返回default"""
    try:
        r = page.run_js(script)
        return r if r is not None else default
    except:
        return default


def get_page_text(page):
    """获取页面可见文本(全部innerText)"""
    return js(page, "return document.body?.innerText || ''", "")


def get_page_title(page):
    """获取页面标题(纯JS, 不触发导航)"""
    return js(page, "return document.title || ''", "")


def is_page_loaded(page):
    """页面基本加载完成"""
    state = js(page, "return document.readyState || ''", "")
    return state == "complete"


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
            w, h = random.randint(1200, 1600), random.randint(800, 1000)
            co.set_argument(f"--window-size={w},{h}")
            page = ChromiumPage(co)
            page.get("https://www.zhipin.com/web/geek/job?city=101010100")
            time.sleep(random.uniform(3, 5))
            title = get_page_title(page)
            log(f"✓ Edge连接成功, 标题: {title[:50]}")
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

def human_mouse_move(page):
    """模拟鼠标随机移动"""
    try:
        w = js(page, "return window.innerWidth", 1200)
        h = js(page, "return window.innerHeight", 800)
        x = random.randint(100, max(200, w - 200))
        y = random.randint(200, max(300, h - 300))
        for step in range(random.randint(2, 5)):
            tx = x + random.randint(-50, 50)
            ty = y + random.randint(-30, 30)
            js(page, f"""
                var ev = new MouseEvent('mousemove', {{
                    clientX: {tx}, clientY: {ty},
                    bubbles: true, cancelable: true
                }});
                var el = document.elementFromPoint({tx},{ty});
                if(el) el.dispatchEvent(ev);
            """)
            time.sleep(random.uniform(0.1, 0.4))
    except:
        pass


def human_scroll(page):
    """模拟真人浏览滚动"""
    try:
        js(page, f"window.scrollBy({{top: {random.randint(150,500)}, behavior: 'smooth'}})")
    except:
        pass
    time.sleep(random.uniform(0.8, 2.0))
    try:
        js(page, f"window.scrollBy({{top: {random.randint(400,900)}, behavior: 'smooth'}})")
    except:
        pass
    time.sleep(random.uniform(0.5, 1.5))
    if random.random() < 0.3:
        try:
            js(page, f"window.scrollBy({{top: {random.randint(-200,-50)}, behavior: 'smooth'}})")
        except:
            pass
        time.sleep(random.uniform(0.5, 1.0))


# ==================== 验证码检测 ====================

def check_captcha(page):
    """纯JS检测风控"""
    try:
        title = get_page_title(page)
        # 只看标题(长度短, 可靠)
        for kw in CAPTCHA_KEYWORDS:
            if kw in title:
                return True, f"标题含'{kw}': {title[:60]}"
        # 仅在body极短时(真验证页特征)扫关键词, 避免长页正文误判
        body = js(page, "return document.body?.innerText?.slice(0,200) || ''", "")
        if len(body) < 200:
            for kw in ["安全验证", "人机验证", "验证码", "请完成验证", "滑块验证"]:
                if kw in body:
                    return True, f"短body含'{kw}'"
        return False, ""
    except:
        return False, ""


def handle_captcha(page):
    """弹窗通知, 等用户手动完成验证"""
    log("\n" + "!" * 50)
    log("!!! 检测到验证码/风控 !!!")
    log("!" * 50)
    ctypes.windll.user32.MessageBoxW(
        0,
        "Boss直聘触发了验证码!\n\n请在Edge中手动完成验证,\n然后点击确定继续抓取。",
        "验证码!", 0x00001000 | 0x00000030
    )
    log("等待手动验证...")
    while True:
        time.sleep(5)
        is_captcha, detail = check_captcha(page)
        if not is_captcha:
            log("✓ 验证已通过, 继续抓取")
            rest = random.randint(30, 60)
            log(f"   休息 {rest} 秒后再继续...")
            time.sleep(rest)
            return
        log(f"   仍在验证中... ({detail})")


# ==================== JD提取核心 ====================

def wait_for_jd_render(page):
    """等待SPA渲染完成 — 纯innerText检测"""
    deadline = time.time() + RENDER_TIMEOUT
    while time.time() < deadline:
        # 验证码
        is_cap, _ = check_captcha(page)
        if is_cap:
            return "captcha"

        # 读取页面文本
        body = get_page_text(page)

        # 检测页面是否显示"职位不存在"(精确匹配, 避免误判)
        # 只在body较短(<500字符)时才算过期
        if len(body) < 500:
            if any(kw in body for kw in ["该职位已不存在", "该职位已过期", "职位已关闭",
                                          "该职位不存在", "该职位可能已关闭"]):
                return "expired"

        # 检测JD是否已渲染 — 关键词 + 长度 > 200
        if len(body) > 200:
            has_kw = any(kw in body for kw in ["职位描述", "岗位职责", "任职要求", "岗位要求"])
            if has_kw:
                return "ready"

        # body已经很长了(>2000)但没关键词 → 可能是其他页面, 算ready让extraction尝试
        if len(body) > 2000:
            return "ready"

        time.sleep(0.5)

    # 超时 → 尝试直接提取
    body = get_page_text(page)
    if len(body) > 100:
        return "ready"
    return "timeout"


def extract_jd_from_text(page):
    """从innerText中智能提取JD文本 — 不依赖任何CSS选择器"""
    body = get_page_text(page)
    if not body or len(body) < 50:
        return ""

    lines = [l.strip() for l in body.split("\n") if l.strip()]

    # ========== 方案A: 找"职位描述"或"岗位职责"行, 向后取2000字 ==========
    keywords = ["职位描述", "岗位职责", "任职要求", "岗位要求", "工作内容"]
    start_idx = None
    for i, line in enumerate(lines):
        # 精确行匹配: 行以这些词开头, 或者行就是这些词(标题行)
        for kw in keywords:
            if line == kw or line.startswith(kw):
                start_idx = i
                break
        if start_idx is not None:
            break

    # 如果单行没找到, 试试在行内包含关键词
    if start_idx is None:
        for i, line in enumerate(lines):
            if any(kw in line for kw in keywords):
                start_idx = i
                break

    if start_idx is not None:
        jd_lines = []
        total = 0
        for line in lines[start_idx:]:
            # 停止条件: 遇到下一个区块标题(不是JD的部分)
            stop_kw = ["公司介绍", "工商信息", "工作地址", "职位分析", "BOSS主页",
                       "公司基本信息", "查看更多", "工作体验", "职位发布者",
                       "看了此职位的人", "公司相册", "热门职位", "Boss 直聘"]
            if any(line.startswith(kw) or line == kw for kw in stop_kw) and total > 300:
                break
            jd_lines.append(line)
            total += len(line)
            if total > 2500:
                break
        result = "\n".join(jd_lines)
        # JD通常>50字
        if len(result) > 50:
            # 去掉太短的结果(可能只是标题文字)
            return result

    # ========== 方案B: 按段落找包含关键词的长段落 ==========
    paragraphs = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 60]
    for p in paragraphs:
        if any(kw in p for kw in ["任职", "岗位", "职责", "要求", "经验", "学历"]):
            if len(p) > 80:
                return p

    # ========== 方案C: 最后兜底 — 只要body够长, 返回全文 ==========
    if len(body) > 300:
        # 截取开头到"公司介绍"之间
        idx = body.find("公司介绍")
        if idx > 200:
            return body[:idx].strip()
        return body[:3000]

    return ""


# ==================== 反封禁辅助 ====================

def restart_edge_browser():
    """重启Edge浏览器进程(调试模式)"""
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


def reconnect_page(page):
    """检测连接状态, 断开则重新连接(含Edge重启)"""
    try:
        js(page, "return document.title || ''")
        return page
    except:
        pass

    log("  ⚠ 连接断开, 重启Edge并重连...")
    for attempt in range(5):
        try:
            restart_edge_browser()
            co = ChromiumOptions()
            co.set_local_port(DEBUG_PORT)
            co.set_browser_path(EDGE_PATH)
            page = ChromiumPage(co)
            page.get("https://www.zhipin.com/web/geek/job?city=101010100")
            time.sleep(random.uniform(2, 3))
            log("  ✓ 重连成功")
            return page
        except Exception as e:
            log(f"  重连尝试 {attempt+1}/5: {e}")
            time.sleep(5)
    raise RuntimeError("重连失败(已重启Edge)")


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
        safe_navigate(page, "https://www.zhipin.com/web/geek/job?city=101010100")
    except:
        pass
    time.sleep(random.uniform(2, 4))
    for _ in range(random.randint(1, 3)):
        human_scroll(page)
    if random.random() < 0.3:
        try:
            w = js(page, "return window.innerWidth", 1200)
            h = js(page, "return window.innerHeight", 800)
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
    log("=== BOSS JD V7 纯JS提取版 ===")
    log(f"   间隔: {GAP_MIN}-{GAP_MAX}s | 停留: {STAY_MIN}-{STAY_MAX}s")
    log(f"   渲染超时: {RENDER_TIMEOUT}s | 重试回退: {RETRY_BACKOFF}s")
    log(f"   每{HOME_REFRESH}条回列表页 | 提取方式: 纯innerText")
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
        f"BOSS直聘 JD全量抓取 V7\n"
        f"提取方式: 纯JS innerText (不依赖CSS选择器)\n\n"
        f"✅ 已完成: {len(done_ids)}\n"
        f"📋 待抓取: {len(pending)}\n"
        f"⏱ 预估: {len(pending)*9//3600} 小时\n\n"
        f"⚠ 如遇验证码会弹窗暂停\n"
        f"请在Edge中点击'确定'开始",
        "BOSS JD V7", 0x00001000 | 0x00000040
    )

    success = 0
    fail    = 0
    expired = 0
    last_home = 0
    start_time = time.time()

    log("开始抓取!\n")

    for idx, rec in enumerate(pending):
        jid = rec["encryptJobId"]

        # ======== 验证码检查 ========
        is_captcha, detail = check_captcha(page)
        if is_captcha:
            handle_captcha(page)
            last_home = 0

        # ======== 随机间隔 ========
        gap = random.uniform(GAP_MIN, GAP_MAX)
        # 8%概率长间隔(模拟离开工位)
        if random.random() < 0.08:
            gap += random.uniform(5, 12)
        time.sleep(gap)

        # ======== 导航 ========
        url = f"https://www.zhipin.com/job_detail/{jid}.html"
        try:
            page = safe_navigate(page, url)
        except Exception as e:
            log(f"  ✗ 导航失败: {e} | {jid[:20]}...")
            fail += 1
            save_jd(jid, "")
            continue

        # ======== 验证码检查(打开后立即检查) ========
        is_captcha, detail = check_captcha(page)
        if is_captcha:
            log(f"  ⚠ 检测到验证码: {detail}")
            handle_captcha(page)
            last_home = 0
            try:
                page = safe_navigate(page, url)
                time.sleep(3)
            except:
                fail += 1
                save_jd(jid, "")
                continue
            is_captcha, _ = check_captcha(page)
            if is_captcha:
                fail += 1
                save_jd(jid, "")
                continue

        # ======== 模拟真人行为 ========
        human_mouse_move(page)
        time.sleep(random.uniform(0.3, 1.0))
        human_scroll(page)

        # 停留阅读
        stay = random.uniform(STAY_MIN, STAY_MAX)
        if random.random() < 0.05:
            stay += random.uniform(3, 8)
        time.sleep(stay)

        # 偶尔回翻
        if random.random() < 0.25:
            try:
                js(page, f"window.scrollBy({{top: {random.randint(-300,-50)}, behavior: 'smooth'}})")
            except:
                pass
            time.sleep(random.uniform(0.5, 1.5))

        # ======== 读取JD (新方案: 纯JS提取) ========
        status = wait_for_jd_render(page)

        if status == "captcha":
            handle_captcha(page)
            time.sleep(2)
            status = wait_for_jd_render(page)

        if status == "expired":
            save_jd(jid, "")
            expired += 1
            if idx < 10:
                log(f"  - 职位已过期 | {jid[:20]}...")
            continue

        jd_text = extract_jd_from_text(page)

        if jd_text and len(jd_text) > 50:
            save_jd(jid, jd_text)
            success += 1
            if (success + fail + expired) % 50 == 0:
                log(f"  ✓ {len(jd_text)}字 | 成功{success} 失败{fail} 过期{expired}")
        else:
            # 重试: 等几秒再读
            time.sleep(random.uniform(3, 6))
            human_scroll(page)
            time.sleep(2)
            jd_text = extract_jd_from_text(page)
            if jd_text and len(jd_text) > 50:
                save_jd(jid, jd_text)
                success += 1
            else:
                save_jd(jid, "")
                fail += 1
                if (success + fail + expired) <= 10 or (success + fail + expired) % 50 == 0:
                    log(f"  - 无JD | 失败{fail} | {jid[:20]}...")

        total_done = success + fail + expired

        # ======== 定期回列表页 ========
        if (total_done - last_home) >= HOME_REFRESH:
            log(f"  [逛列表页...]")
            browse_list_page(page)
            last_home = total_done

        # ======== 进度报告 ========
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
    log(f"   速率: {total_done/elapsed:.2f}条/s")
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