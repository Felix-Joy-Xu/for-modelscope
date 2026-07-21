"""Boss Zhipin programmer jobs crawler — 爬取所有程序员相关岗位。

Strategy:
    用 30+ 技术关键词分别搜索，每个关键词翻完所有结果页。
    从职位卡片提取基本信息，点击卡片后从右侧详情面板提取完整 JD。

Usage:
    python boss_programmer.py

Output: D:\hiring_data\boss_programmer\
"""
import json
import time
import ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

OUT_DIR = Path("D:/hiring_data/boss_programmer")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 技术角色关键词（覆盖程序员主要方向）
KEYWORDS = [
    "后端开发", "前端开发", "Java开发", "Python开发",
    "Go开发", "C++开发", "算法工程师", "AI工程师",
    "大数据", "数据分析", "测试开发", "运维开发",
    "全栈", "Android开发", "iOS开发", "客户端开发",
    "架构师", "技术经理", "技术总监", "DevOps",
    "数据库", "云计算", "安全工程师", "嵌入式开发",
    "区块链", "游戏开发", "音视频", "NLP",
    "计算机视觉", "深度学习", "自动驾驶", "量化开发",
]

CITY_CODE = "100010000"      # 全国
PAGE_DELAY = 3.5
CARD_CLICK_DELAY = 1.2
DETAIL_WAIT = 1.5
MAX_EMPTY = 3
MAX_PAGES_PER_KW = 15       # Boss 通常限制 ~10-15 页


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def login(page):
    page.get(f"https://www.zhipin.com/web/geek/job?city={CITY_CODE}")
    time.sleep(3)
    ctypes.windll.user32.MessageBoxW(
        0,
        "请扫码登录 Boss 直聘\n完成验证后\n职位列表正常显示\n点击 [确定] 开始抓取",
        "登录",
        0x00001000 | 0x00000040,
    )
    log("已确认登录")


def search(page, keyword):
    url = f"https://www.zhipin.com/web/geek/job?query={keyword}&city={CITY_CODE}"
    page.get(url)
    time.sleep(4)


def get_cards(page):
    """获取当前页所有职位卡片 (li.job-card-box)。"""
    for sel in [
        "li.job-card-box",
        ".job-card-box",
    ]:
        try:
            cards = page.eles(sel, timeout=3)
            if cards:
                return cards
        except:
            continue
    # 兜底
    try:
        ul = page.ele("ul.rec-job-list", timeout=2)
        if ul:
            return ul.eles("tag:li")
    except:
        pass
    return []


def extract_from_card(card):
    """从卡片 DOM 提取基本信息（不点击）。"""
    data = {}

    # 标题
    name_el = card.ele("a.job-name", timeout=0.5)
    if not name_el:
        name_el = card.ele('[class*="job-name"]', timeout=0.3)
    if name_el:
        data["title"] = name_el.text.strip()

    # 薪资
    sal_el = card.ele('[class*="salary"]', timeout=0.3)
    if not sal_el:
        sal_el = card.ele(".red", timeout=0.3)
    if sal_el:
        data["salary"] = sal_el.text.strip()

    # 公司
    comp_el = card.ele("h3.company-name a", timeout=0.3)
    if not comp_el:
        comp_el = card.ele('[class*="company-name"]', timeout=0.3)
    if comp_el:
        data["company"] = comp_el.text.strip()

    # 经验/学历
    limit_el = card.ele(".job-limit", timeout=0.3)
    if limit_el:
        data["requirement"] = limit_el.text.strip().replace("\n", " ")
    else:
        # 从 p 标签找
        ps = card.eles("tag:p", timeout=0.3)
        reqs = [p.text.strip() for p in ps if p.text.strip()]
        data["requirement"] = " ".join(reqs) if reqs else ""

    # 标签
    tag_els = card.eles("tag:span", timeout=0.3)
    tags = [t.text.strip() for t in tag_els if t.text.strip()]
    data["tags"] = tags

    return data if "title" in data and data["title"] else None


def extract_detail_from_panel(page):
    """从右侧详情面板提取完整 JD。"""
    detail = {}
    for sel in [".job-detail-section", ".detail-content", ".job-desc", ".job-detail-container", ".job-sec-text"]:
        el = page.ele(sel, timeout=2)
        if el:
            detail["jd_text"] = el.text.strip()[:8000]
            break
    if "jd_text" not in detail:
        detail["jd_text"] = ""
    return detail


def click_next(page):
    """翻下一页，返回 True 成功 / False 末页。"""
    # Boss 直聘分页在页面底部
    candidates = []
    for sel in [".ui-icon-arrow-right", ".next", '[class*="next"]']:
        try:
            els = page.eles(sel, timeout=1)
            candidates.extend(els)
        except:
            pass

    for btn in candidates:
        parent = btn.parent()
        if parent:
            cls = (parent.attr("class") or "") + (btn.attr("class") or "")
            if "disabled" in cls or "disable" in cls.lower():
                continue
        try:
            btn.click()
            time.sleep(PAGE_DELAY)
            return True
        except:
            pass

    # 尝试找分页链接中的下一页
    try:
        pagination = page.ele(".options-pages", timeout=1)
        if pagination:
            last = pagination.ele("a:last-of-type", timeout=0.5)
            if last:
                last.click()
                time.sleep(PAGE_DELAY)
                return True
    except:
        pass

    return False


def scrape_keyword(page, keyword, outpath):
    """搜索并抓取一个关键词的所有结果页。"""
    log(f"\n{'─'*50}")
    log(f"关键词: {keyword}")
    log(f"{'─'*50}")

    search(page, keyword)

    records = []
    seen = set()
    page_num = 1
    empty_count = 0

    while empty_count < MAX_EMPTY and page_num <= MAX_PAGES_PER_KW:
        log(f"  第 {page_num} 页 ...")
        cards = get_cards(page)

        if not cards:
            empty_count += 1
            log(f"    无卡片 ×{empty_count}")
            if empty_count >= MAX_EMPTY:
                break
            ok = click_next(page)
            if not ok:
                break
            page_num += 1
            continue
        empty_count = 0

        # 第一张卡片先点开触发右侧面板
        if cards:
            try:
                cards[0].click()
                time.sleep(CARD_CLICK_DELAY + DETAIL_WAIT)
            except:
                pass

        for card in cards:
            try:
                card.scroll_to_see()
                time.sleep(0.15)
                card.click()
                time.sleep(CARD_CLICK_DELAY)

                base = extract_from_card(card)
                if not base:
                    continue

                key = base.get("title", "") + base.get("company", "")[:20]
                if key in seen:
                    continue
                seen.add(key)

                detail = extract_detail_from_panel(page)
                base["jd_text"] = detail.get("jd_text", "")
                base["search_kw"] = keyword
                base["crawl_ts"] = datetime.now(timezone.utc).isoformat()
                records.append(base)
            except:
                pass

        log(f"    已提取 {len(records)} 条")

        ok = click_next(page)
        if not ok:
            log("    已达末页")
            break
        page_num += 1

    # 写入
    with open(outpath, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    log(f"✓ {keyword}: {len(records)} 条 -> {outpath.name}")
    return len(records)


def main():
    log("启动浏览器...")
    page = ChromiumPage()
    login(page)

    grand_total = 0
    for kw in KEYWORDS:
        safe_name = kw.replace("/", "_").replace(" ", "_")
        outpath = OUT_DIR / f"{safe_name}.jsonl"

        # 跳过已完成的
        if outpath.exists() and outpath.stat().st_size > 100:
            lines = outpath.read_text(encoding="utf-8").strip().split("\n")
            cnt = len([l for l in lines if l.strip()])
            log(f"  [跳过] {kw} — 已有 {cnt} 条")
            grand_total += cnt
            continue

        try:
            cnt = scrape_keyword(page, kw, outpath)
            grand_total += cnt
        except Exception as e:
            log(f"✗ [{kw}] 出错: {e}")
            import traceback
            traceback.print_exc()
            continue

    # 去重汇总
    all_jobs = {}
    for f in sorted(OUT_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                j = json.loads(line)
                key = (j.get("title", "") + j.get("company", ""))[:100]
                if key not in all_jobs:
                    all_jobs[key] = j
            except:
                pass

    merged_path = OUT_DIR / "_all_unique.jsonl"
    with open(merged_path, "w", encoding="utf-8") as f:
        for j in all_jobs.values():
            f.write(json.dumps(j, ensure_ascii=False) + "\n")

    log(f"\n{'='*60}")
    log(f"总计原始: {grand_total} 条")
    log(f"去重后:   {len(all_jobs)} 条")
    log(f"汇总文件: {merged_path}")
    log(f"输出目录: {OUT_DIR}")
    log(f"{'='*60}")

    print("\n各关键词汇总:")
    for f in sorted(OUT_DIR.glob("*.jsonl")):
        if f.stem.startswith("_"):
            continue
        lines = f.read_text(encoding="utf-8").strip().split("\n")
        cnt = len([l for l in lines if l.strip()])
        print(f"  {f.stem:30s} {cnt:4d} 条")
    print(f"  {'─'*38}")
    print(f"  {'去重后合计':30s} {len(all_jobs):4d} 条")

    log("\n浏览器保持打开。")


if __name__ == "__main__":
    main()