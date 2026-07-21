"""Boss 直聘技术类全量抓取 - 最终版

启动后弹出扫码窗口 → 用户扫码登录 → 点确定 → 自动抓取

核心策略（三层保障）:
  1) 优先用 URL 参数 position=100000 直接筛选
  2) 如果无效，在页面筛选栏里点击"技术"按钮
  3) 还不行就用关键词搜索兜底

数据字段: title, salary, company, requirement, tags, jd_text
输出: D:\hiring_data\boss_tech_final\tech_all.jsonl
"""
import json, time, ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

# ─────────────────── 配置 ───────────────────
OUT_DIR = Path("D:/hiring_data/boss_tech_final")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "tech_all.jsonl"

CITY = "100010000"          # 全国
POSITION = "100000"         # 技术大类
PAGE_DELAY = 3.0
CARD_DELAY = 1.2
MAX_PAGES = 400
MAX_EMPTY = 4

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


# ───────────── 登录 ─────────────
def wait_login(page):
    page.get(f"https://www.zhipin.com/web/geek/job?city={CITY}")
    time.sleep(3)
    ctypes.windll.user32.MessageBoxW(
        0,
        "请在浏览器扫码登录 Boss 直聘\n\n点击 [确定] 开始抓取",
        "登录",
        0x00001000 | 0x00000040,
    )
    log("已确认登录")


# ───────────── 卡片提取 ─────────────
def get_cards(page):
    for sel in ["li.job-card-box", ".job-card-box"]:
        try:
            cards = page.eles(sel, timeout=4)
            if cards:
                return cards
        except:
            continue
    try:
        ul = page.ele("ul.rec-job-list", timeout=2)
        if ul:
            return ul.eles("tag:li")
    except:
        pass
    return []


def extract_card(card):
    d = {}
    name = card.ele("a.job-name", timeout=0.5)
    if not name:
        name = card.ele('[class*="job-name"]', timeout=0.3)
    if not name:
        return None
    d["title"] = name.text.strip()

    sal = card.ele('[class*="salary"]', timeout=0.3)
    if sal:
        d["salary"] = sal.text.strip().replace("\n", " ")

    comp = card.ele('[class*="company-name"]', timeout=0.3)
    if comp:
        d["company"] = comp.text.strip()

    limit = card.ele(".job-limit", timeout=0.3)
    if limit:
        d["requirement"] = limit.text.strip().replace("\n", " ")

    spans = card.eles("tag:span", timeout=0.3)
    d["tags"] = [s.text.strip() for s in spans if s.text.strip()]

    return d


def extract_detail(page):
    for sel in [
        ".job-detail-section", ".detail-content", ".job-desc",
        ".job-detail-container", ".job-sec-text",
    ]:
        el = page.ele(sel, timeout=2)
        if el and el.text.strip():
            return el.text.strip()[:8000]
    return ""


def click_next(page):
    for sel in [".ui-icon-arrow-right", '[class*="next"]']:
        btn = page.ele(sel, timeout=1.5)
        if not btn:
            continue
        parent = btn.parent()
        cls = (parent.attr("class") or "") if parent else ""
        if "disabled" in cls or "disable" in cls.lower():
            continue
        btn.click()
        time.sleep(PAGE_DELAY)
        return True
    pager = page.ele(".options-pages", timeout=1)
    if pager:
        last = pager.ele("a:last-of-type", timeout=0.5)
        if last:
            last.click()
            time.sleep(PAGE_DELAY)
            return True
    return False


# ───────────── 翻页抓取 ─────────────
def scrape_pages(page, label):
    """在当前筛选结果下翻页抓取, 返回记录列表。"""
    seen = set()
    records = []
    page_num = 1
    empty_cnt = 0

    while empty_cnt < MAX_EMPTY and page_num <= MAX_PAGES:
        log(f"  [{label}] 第 {page_num} 页")
        cards = get_cards(page)
        if not cards:
            empty_cnt += 1
            log(f"    无卡片 ×{empty_cnt}")
            if empty_cnt >= MAX_EMPTY:
                break
            page_num += 1
            if not click_next(page):
                break
            continue
        empty_cnt = 0

        log(f"    卡片: {len(cards)}")
        try:
            cards[0].click()
            time.sleep(2)
        except:
            pass

        for card in cards:
            try:
                card.scroll_to_see()
                time.sleep(0.15)
                card.click()
                time.sleep(CARD_DELAY)
                base = extract_card(card)
                if not base:
                    continue
                key = base["title"] + (base.get("company") or "")[:30]
                if key in seen:
                    continue
                seen.add(key)
                base["jd_text"] = extract_detail(page)
                base["crawl_ts"] = datetime.now(timezone.utc).isoformat()
                records.append(base)
            except:
                pass

        log(f"    已抓 {len(records)}")
        if not click_next(page):
            log("    已达末页")
            break
        page_num += 1

    return records


# ───────────── 写文件 ─────────────
def save_records(records, mode="a"):
    with open(OUT_PATH, mode, encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ───────────── 主流程 ─────────────
def main():
    log("启动浏览器")
    page = ChromiumPage()
    wait_login(page)

    all_seen = set()

    # 断点续抓: 读取已有数据
    existing = 0
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    j = json.loads(line)
                    key = j.get("title", "") + (j.get("company", "") or "")[:30]
                    all_seen.add(key)
                except:
                    pass
        existing = len(all_seen)
        log(f"已有数据: {existing} 条 (断点续抓)")

    all_records = []

    # ── 第1层: 尝试 URL 参数 position=100000 ──
    log("\n" + "=" * 50)
    log("第1层: 尝试 URL 参数 position=100000")
    url = f"https://www.zhipin.com/web/geek/job?city={CITY}&position={POSITION}"
    page.get(url)
    time.sleep(5)
    cards = get_cards(page)
    if cards:
        log(f"  有效! 检测到 {len(cards)} 张卡片")
        recs = scrape_pages(page, "position-url")
        for r in recs:
            key = r["title"] + (r.get("company") or "")[:30]
            if key not in all_seen:
                all_seen.add(key)
                all_records.append(r)
        save_records(recs)
    else:
        log("  position 参数未生效, 进入第2层")

    # ── 第2层: 在页面筛选栏里点"技术" ──
    log("\n" + "=" * 50)
    log("第2层: DOM 点击'技术'分类")
    page.get(f"https://www.zhipin.com/web/geek/job?city={CITY}")
    time.sleep(5)

    # 找筛选栏里所有可点击元素
    clicked = False
    for el in page.eles("tag:span", timeout=3):
        text = (el.text or "").strip()
        if text == "技术":
            try:
                el.click()
                time.sleep(4)
                log("  已点击'技术'分类")
                clicked = True
                break
            except:
                pass

    if clicked:
        cards = get_cards(page)
        if cards:
            log(f"  有效! {len(cards)} 张卡片")
            recs = scrape_pages(page, "tech-click")
            for r in recs:
                key = r["title"] + (r.get("company") or "")[:30]
                if key not in all_seen:
                    all_seen.add(key)
                    all_records.append(r)
            save_records(recs)
        else:
            log("  点击后仍未检测到卡片")

    if all_records:
        log(f"\n第1-2层共抓取 {len(all_records)} 条 (去重)")
    else:
        # ── 第3层: 关键词搜索兜底 ──
        log("\n" + "=" * 50)
        log("第3层: 关键词搜索兜底")
        for i, kw in enumerate(TECH_KW, 1):
            if len(all_records) >= 3000:
                log(f"  已超 3000 条, 跳过剩余关键词")
                break
            log(f"\n  [{i}/{len(TECH_KW)}] 关键词: {kw}")
            url = f"https://www.zhipin.com/web/geek/job?query={kw}&city={CITY}"
            page.get(url)
            time.sleep(4)
            cards = get_cards(page)
            if not cards:
                log("    无结果")
                continue
            recs = scrape_pages(page, kw)
            new_cnt = 0
            for r in recs:
                key = r["title"] + (r.get("company") or "")[:30]
                if key not in all_seen:
                    all_seen.add(key)
                    all_records.append(r)
                    new_cnt += 1
            log(f"    新增 {new_cnt} 条 (累计 {len(all_records)})")
            save_records(recs)

    # ── 最终汇总 ──
    log(f"\n{'=' * 60}")
    log(f"抓取完成! 总计去重后: {len(all_records)} 条")
    log(f"输出文件: {OUT_PATH}")
    log(f"{'=' * 60}")
    log("浏览器保持打开, 手动关闭即可。")


if __name__ == "__main__":
    main()