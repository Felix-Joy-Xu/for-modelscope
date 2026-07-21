import json
import time
import random
import ctypes
from pathlib import Path
from DrissionPage import ChromiumPage

# ================= 配置区 =================
SOURCE_FILE = Path(r"D:\hiring_data\boss_api\tech_jobs_grid_72k.jsonl")
JD_OUTPUT_FILE = Path(r"D:\hiring_data\boss_api\boss_jd_data.jsonl")
DELAY_MIN = 3.0
DELAY_MAX = 7.0
# ==========================================

def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def msg_box(title, text):
    ctypes.windll.user32.MessageBoxW(0, text, title, 1)

def wait_login(page: ChromiumPage):
    log("正在等待用户确认登录状态...")
    msg_box("启动 JD 详情页爬虫", "请确认 Chrome 浏览器中已成功登录 Boss 直聘，且能正常显示页面。\n准备好后请点击确定开始提取 JD。")
    log("已确认登录，开始全速抓取 JD！")

def load_source_ids():
    ids = []
    if not SOURCE_FILE.exists():
        log(f"源文件 {SOURCE_FILE} 不存在！")
        return ids
        
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                data = json.loads(line)
                jid = data.get("encryptJobId")
                if jid:
                    ids.append(jid)
            except:
                pass
    # 去重处理，保留唯一 ID
    unique_ids = list(dict.fromkeys(ids))
    log(f"成功加载 {len(unique_ids)} 个唯一岗位 ID")
    return unique_ids

def load_existing_jds():
    existing_ids = set()
    if JD_OUTPUT_FILE.exists():
        with open(JD_OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    existing_ids.add(data["encryptJobId"])
                except:
                    pass
    log(f"已发现 {len(existing_ids)} 个已经成功抓取的 JD 记录，自动跳过。")
    return existing_ids

def scrape_jd(page: ChromiumPage, jid: str):
    url = f"https://www.zhipin.com/job_detail/{jid}.html"
    page.get(url)
    
    # 随机休眠以规避反爬
    sleep_time = random.uniform(DELAY_MIN, DELAY_MAX)
    time.sleep(sleep_time)
    
    # 检查是否遇到验证码或被拦截
    if "验证" in page.title or "安全" in page.title or page.ele('.verification-code', timeout=1) or page.ele('#wrap', timeout=1):
        if page.ele('.job-sec-text', timeout=1):
            pass # 页面正常
        else:
            log("!!! 警告：可能触发了风控滑块验证，脚本自动暂停 !!!")
            msg_box("触发风控拦截", "页面可能跳转到了滑块验证或登录过期，请手动在浏览器中处理。\n处理完毕并看到正常详情页后，再点击此确定按钮继续。")
    
    # 提取 JD
    jd_ele = page.ele('.job-sec-text', timeout=2)
    if not jd_ele:
        # 如果依然没有找到，记录空并返回（可能是岗位下线了）
        log(f"警告：找不到 JD 文本 (ID: {jid})，可能该岗位已关闭或被隐藏。")
        return ""
        
    return jd_ele.text

def main():
    log("=== Boss 直聘 JD 详情页长文本全量抓取 ===")
    
    source_ids = load_source_ids()
    if not source_ids:
        return
        
    existing_ids = load_existing_jds()
    
    page = ChromiumPage()
    
    # 打开首页测试登录状态
    page.get("https://www.zhipin.com/")
    wait_login(page)
    
    total = len(source_ids)
    success_count = 0
    fail_count = 0
    
    with open(JD_OUTPUT_FILE, "a", encoding="utf-8") as fout:
        for idx, jid in enumerate(source_ids, 1):
            if jid in existing_ids:
                continue
                
            log(f"[{idx}/{total}] 正在抓取: {jid}")
            
            try:
                jd_text = scrape_jd(page, jid)
                if jd_text:
                    record = {
                        "encryptJobId": jid,
                        "jd_text": jd_text,
                        "crawl_ts": time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
                    }
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fout.flush()
                    success_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                log(f"抓取异常: {e}")
                # 如果发生底层的断开连接，抛出让脚本彻底崩溃以便我们重启
                if "PageDisconnectedError" in str(type(e)):
                    log("浏览器断开连接，脚本安全退出。")
                    raise e
                time.sleep(5)
                
    log("=" * 60)
    log(f"本次运行抓取完毕！成功抓取: {success_count} 条，失败/失效: {fail_count} 条。")
    log(f"数据保存在: {JD_OUTPUT_FILE}")

if __name__ == "__main__":
    main()
