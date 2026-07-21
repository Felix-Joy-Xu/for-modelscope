"""Boss直聘技术类职位全量爬虫 — 使用职位分类筛选

策略:
    1. 扫码登录后，通过筛选栏选中"技术"分类
    2. 自动翻页抓取所有结果
    3. 基于已验证的 DOM 结构: li.job-card-box / a.job-name

Usage:
    python boss_tech_only.py

Output: D:\hiring_data\boss_tech_only\
"""
import json
import time
import ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

OUT_DIR = Path("D:/hiring_data/boss_tech_only")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Boss直聘职位分类的 URL 参数 (技术类及子类)
# 当 position=100000 时, API 返回所有技术类职位
POSITION_CODE = "100000"       # 技术大类
CITY_CODE = "100010000"        # 全国
PAGE_DELAY = 3
CARD_DELAY = 1.2
MAX_PAGES = 300
MAX_CONSEC_EMPTY = 4

OUT_PATH = OUT_DIR / "tech_jobs.jsonl"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def wait_login(page):
    """弹窗等待用户扫码登录。"""
    page.get(f"https://www.zhipin.com/web/geek/job?city={CITY_CODE}")
    time.sleep(3)
    ctypes.windll.user32.MessageBoxW(
        0,
        "请在浏览器里扫码登录 Boss 直聘\n\n完成后点击 [确定] 开始抓取",
        "Boss 直聘登录",
        0x00001000 | 0x00000040,
    )
    log("用户已确认登录")


def select_tech_category(page):
    """尝试在筛选栏里选中"技术"分类。

    策略: 默认展示的就是不限分类的全部结果, 我们可以在 URL 上追加
    position=100000 参数直接筛选技术类, 比 DOM 点击更可靠。
    """
    # 方案 A: 直接用带 position 参数的 URL
    url = f"https://www.zhipin.com/web/geek/job?city={CITY_CODE}&position={POSITION_CODE}"
    page.get(url)
    time.sleep(5)
    log("已用 position=100000 加载技术类职位")

    # 方案 B: 如果上面没生效, 尝试点击筛选栏
    cards = get_cards(page)
    if not cards:
        log("position 参数可能未生效, 尝试 DOM 点击分类...")
        # 回到搜索页, 手动点击分类
        page.get(f"https://www.zhipin.com/web/geek/job?city={CITY_CODE}")
        time.sleep(4)
        # 找筛选栏中可能包含 "技术" 的按钮
        for btn in page.eles("tag:span", timeout=2):
            if "技术" in (btn.text or ""):
                try:
                    btn.click()
                    time.sleep(3)
                    log("  -> 已点击技术分类")
                    break
                except:
                    pass


def get_cards(page):
    """获取当前页的所有职位卡片。"""
    # 已验证的选择器
    for sel in ["li.job-card-box", ".job-card-box"]:
        try:
            cards = page.eles(sel, timeout=4)
            if cards:
                return cards
        except:
            continue
    # 兜底: ul.rec-job-list 下的 li
    try:
        ul = page.ele("ul.rec-job-list", timeout=2)
        if ul:
            lis = ul.eles("tag:li")
            if lis:
                return lis
    except:
        pass
    return []


def extract_card(card):
    """从卡片提取职位基本字段。"""
    d = {}
    # 标题
    name = card.ele("a.job-name", timeout=0.5)
    if not name:
        name = card.ele('[class*="job-name"]', timeout=0.3)
    if not name:
        return None
    d["title"] = name.text.strip()

    # 薪资
    salary = card.ele('[class*="salary"]', timeout=0.3)
    if salary:
        d["salary"] = salary.text.strip().replace("\n", " ")

    # 公司
    comp = card.ele('[class*="company-name"]', timeout=0.3)
    if comp:
        d["company"] = comp.text.strip()

    # 要求 (经验/学历)
    limit = card.ele(".job-limit", timeout=0.3)
    if limit:
        d["requirement"] = limit.text.strip().replace("\n", " ")

    # 标签数组
    span_els = card.eles("tag:span", timeout=0.3)
    tags = [s.text.strip() for s in span_els if s.text.strip()]
    d["tags"] = tags

    return d


def extract_detail(page):
    """从右侧详情面板提取 JD 文本。"""
    for sel in [
        ".job-detail-section", ".detail-content", ".job-desc",
        ".job-detail-container", ".job-sec-text",
    ]:
        el = page.ele(sel, timeout=2)
        if el and el.text.strip():
            return el.text.strip()[:8000]
    return ""


def click_next(page):
    """翻下一页, 返回 True/False。"""
    for sel in [".ui-icon-arrow-right", '[class*="next"]']:
        try:
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
        except:
            pass

    # 分页链接
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


def main():
    log("启动浏览器 (Boss 直聘技术类全量抓取)")
    page = ChromiumPage()
    wait_login(page)
    select_tech_category(page)

    # 断点续抓
    existing = 0
    if OUT_PATH.exists():
        lines = OUT_PATH.read_text(encoding="utf-8").strip().split("\n")
        existing = len([l for l in lines if l.strip()])
        log(f"已有数据: {existing} 条, 将追加...")

    records = []
    seen = set()
    page_num = 1
    empty_count = 0

    while empty_count < MAX_CONSEC_EMPTY and page_num <= MAX_PAGES:
        log(f"第 {page_num} 页 ...")
        cards = get_cards(page)

        if not cards:
            empty_count += 1
            log(f"  无卡片 ×{empty_count}")
            if empty_count >= MAX_CONSEC_EMPTY:
                break
            page_num += 1
            try:
                click_next(page)
            except:
                pass
            continue
        empty_count = 0

        log(f"  检测到 {len(cards)} 张卡片")

        # 先点第一张触发右侧面板加载
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

                # 去重 key
                key = base["title"] + (base.get("company", "") or "")[:30]
                if key in seen:
                    continue
                seen.add(key)

                jd = extract_detail(page)
                base["jd_text"] = jd
                base["crawl_ts"] = datetime.now(timezone.utc).isoformat()
                records.append(base)
            except:
                pass

        log(f"  已抓 {len(records)} 条")

        ok = click_next(page)
        if not ok:
            log("  已达末页")
            break
        page_num += 1

    # 保存
    total = existing + len(records)
    with open(OUT_PATH, "a" if existing > 0 else "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    log(f"\n{'='*60}")
    log(f"本次新抓: {len(records)} 条")
    log(f"文件总计: {total} 条")
    log(f"输出文件: {OUT_PATH}")
    log(f"{'='*60}")
    log("浏览器保持打开, 手动关闭即可。")


if __name__ == "__main__":
    main()