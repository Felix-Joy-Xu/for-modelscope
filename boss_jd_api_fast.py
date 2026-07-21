"""BOSS直聘 JD全量抓取 V5 - API极速版 (1.3天跑完7.2万条)
- 纯 API 直调: wapi/zpgeek/job/detail.json
- 零休息、零延迟(仅0.3s间隔防限流)
- Cookie 自动刷新
- 自动重试 + 断点续抓
"""
import json
import time
import os
import subprocess
import traceback
from pathlib import Path
import requests
from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 配置 ====================
SOURCE_PATH = Path(r"D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl")
JD_PATH     = Path(r"D:\hiring_data\boss_api\boss_jd_full.jsonl")
CSV_PATH    = Path(r"D:\hiring_data\boss_api\boss_full_final.csv")
API_URL     = "https://www.zhipin.com/wapi/zpgeek/job/detail.json"
EDGE_PATH   = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT  = 9222
REQUEST_GAP = 0.3          # 请求间隔(秒) — 纯API无需模拟
COOKIE_REFRESH_EVERY = 500 # 每500条刷新cookie
MAX_RETRIES = 3


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ==================== 数据加载 ====================

def load_records():
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
    return records


def load_done():
    """只返回已有真实JD的ID(空JD不算完成,需要重试)"""
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
    return done


def save_jd(jid, jd_text):
    record = {"encryptJobId": jid, "jd_text": jd_text,
              "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")}
    with open(JD_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


# ==================== Cookie 管理 ====================

def get_cookies_from_edge():
    """从Edge浏览器提取cookies"""
    subprocess.run("taskkill /F /IM msedge.exe", shell=True, capture_output=True)
    time.sleep(2)
    
    user_data = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Edge", "User Data")
    cmd = [EDGE_PATH, f"--remote-debugging-port={DEBUG_PORT}",
           f"--user-data-dir={user_data}", "--profile-directory=Default",
           "--no-first-run", "--no-default-browser-check",
           "--disable-blink-features=AutomationControlled"]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    
    co = ChromiumOptions()
    co.set_local_port(DEBUG_PORT)
    co.set_browser_path(EDGE_PATH)
    page = ChromiumPage(co)
    page.get("https://www.zhipin.com/web/geek/job?city=101010100")
    time.sleep(3)
    
    # 检查是否被风控
    title = page.title[:40]
    log(f"Edge: {title}")
    if "验证" in title or "安全" in title:
        log("⚠ 检测到验证页面! 请在Edge中手动完成验证")
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, "Boss需要验证! 请在Edge中完成验证后点确定", "验证", 0x00001000)
        time.sleep(5)
    
    cookies_dict = {}
    for c in page.cookies():
        cookies_dict[c["name"]] = c["value"]
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


# ==================== JD抓取 ====================

def fetch_jd(session, jid, sid):
    """调用API获取JD详情"""
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(
                API_URL,
                params={"jobId": jid, "securityId": sid},
                timeout=15,
                headers={"Referer": f"https://www.zhipin.com/job_detail/{jid}.html"}
            )
            
            if resp.status_code == 403:
                # 可能被限流
                time.sleep(5 * (attempt + 1))
                continue
            
            if resp.status_code != 200:
                time.sleep(2 * (attempt + 1))
                continue
            
            data = resp.json()
            
            # 检查业务错误
            code = data.get("code", -1)
            if code != 0:
                msg = data.get("message", "")
                if "登录" in msg or "验证" in msg or "auth" in msg.lower():
                    return None, "AUTH"  # 需要重新登录
                if attempt < MAX_RETRIES - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                return "", f"API_ERR_{code}:{msg[:50]}"
            
            # 提取JD文本
            job_info = data.get("zpData", {}).get("jobInfo", {})
            if not job_info:
                return "", "NO_JOBINFO"
            
            # JD可能在多个字段中
            jd_text = (
                job_info.get("postDescription", "") or
                job_info.get("jobDetail", "") or
                job_info.get("jobDesc", "") or
                ""
            )
            
            return jd_text, None
            
        except requests.exceptions.Timeout:
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
            else:
                return "", str(e)[:80]
    
    return "", "MAX_RETRIES"


# ==================== 主流程 ====================

def main():
    log("=" * 60)
    log("=== BOSS JD V5 API极速版 ===")
    log(f"API: {API_URL}")
    log(f"间隔: {REQUEST_GAP}s | Cookie刷新: 每{COOKIE_REFRESH_EVERY}条")
    log("=" * 60)
    
    all_records = load_records()
    done_ids    = load_done()
    pending = [r for r in all_records if r["encryptJobId"] not in done_ids]
    
    log(f"总: {len(all_records)} | 已完成: {len(done_ids)} | 待抓: {len(pending)}")
    
    if not pending:
        log("✅ 全部完成!")
        export_csv()
        return
    
    # 获取cookies
    cookies, ua, browser_page = get_cookies_from_edge()
    session = create_session(cookies, ua)
    
    success = 0
    fail    = 0
    empty   = 0
    auth_errs = 0
    consecutive_empty = 0  # 连续空JD计数(仅触发cookie刷新)
    
    start_time = time.time()
    log(f"\n开始抓取! 预计完成: {time.strftime('%m/%d %H:%M', time.localtime(start_time + len(pending)*1.2))}\n")
    
    for idx, rec in enumerate(pending):
        jid = rec["encryptJobId"]
        sid = rec.get("securityId", "")
        
        # Cookie 刷新
        if (idx + 1) % COOKIE_REFRESH_EVERY == 0:
            log(f"\n── 刷新Cookie (已处理{idx+1}条) ──")
            try:
                cookies, ua, _ = get_cookies_from_edge()
                session = create_session(cookies, ua)
                consecutive_empty = 0
            except Exception as e:
                log(f"Cookie刷新失败: {e}, 继续使用旧cookie")
        
        # 连续空JD过多 → 刷新cookie
        if consecutive_empty >= 3:
            log(f"  ⚠ 连续{consecutive_empty}条空JD → 刷新Cookie")
            try:
                cookies, ua, _ = get_cookies_from_edge()
                session = create_session(cookies, ua)
                consecutive_empty = 0
                time.sleep(1)
            except Exception as e:
                log(f"刷新失败: {e}")
        
        # 请求
        jd_text, error = fetch_jd(session, jid, sid)
        
        if error == "AUTH":
            consecutive_empty = 0
            log(f"\n🔐 触发认证! 等待手动处理...")
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "Boss需要重新登录/验证!\n请在Edge中完成操作后点确定", "认证", 0x00001000)
            cookies, ua, _ = get_cookies_from_edge()
            session = create_session(cookies, ua)
            jd_text, error = fetch_jd(session, jid, sid)
            if error:
                fail += 1
                save_jd(jid, "")
                auth_errs += 1
                continue
        
        if jd_text:
            save_jd(jid, jd_text)
            success += 1
            consecutive_empty = 0
        else:
            save_jd(jid, "")
            empty += 1
            consecutive_empty += 1  # 任何空JD都计入,触发cookie刷新
            if idx < 10:
                log(f"  空原因: {error or '无错误(JD字段为空)'}")
        
        if error and error != "AUTH":
            fail += 1
        
        total_done = success + empty
        
        # 进度显示
        if total_done % 50 == 0 or idx < 5:
            elapsed = time.time() - start_time
            rate = total_done / max(elapsed, 1)
            eta_sec = (len(pending) - total_done) / max(rate, 0.01)
            eta_str = f"{eta_sec/3600:.1f}h" if eta_sec > 3600 else f"{eta_sec/60:.0f}m"
            pct = 100 * total_done // len(pending)
            log(f"  [{total_done}/{len(pending)}] {pct}% | 速率:{rate:.1f}/s | "
                f"成功:{success} 空:{empty} | ETA:{eta_str}")
        
        # 极短间隔
        if REQUEST_GAP > 0:
            time.sleep(REQUEST_GAP)
    
    # 收尾
    elapsed = time.time() - start_time
    log(f"\n{'=' * 60}")
    log(f"✅ 完成! 耗时: {elapsed/3600:.1f}h")
    log(f"成功: {success} | 无JD: {empty} | 认证错误: {auth_errs}")
    log(f"速率: {(success+empty)/elapsed:.2f}条/s")
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