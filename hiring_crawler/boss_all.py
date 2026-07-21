"""Boss Zhipin all-companies crawler — 全量抓取 20 家企业招聘职位。

Usage:
    python boss_all.py

Output: D:\hiring_data\boss_all\  (每家企业一个 JSONL)
"""
import json
import time
import ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

OUT_DIR = Path("D:/hiring_data/boss_all")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 20 家目标企业（英文标识 + Boss 搜索关键词）
COMPANIES = [
    ("Bytedance",   "字节跳动"),
    ("Alibaba",     "阿里巴巴"),
    ("Tencent",     "腾讯"),
    ("Meituan",     "美团"),
    ("Pinduoduo",   "拼多多"),
    ("Kuaishou",    "快手"),
    ("Xiaohongshu", "小红书"),
    ("JD",          "京东"),
    ("NetEase",     "网易"),
    ("Baidu",       "百度"),
    ("Huawei",      "华为"),
    ("Xiaomi",      "小米"),
    ("DJI",         "大疆"),
    ("Bilibili",    "哔哩哔哩"),
    ("Didi",        "滴滴"),
    ("AntGroup",    "蚂蚁集团"),
    ("BYD",         "比亚迪"),
    ("NIO",         "蔚来"),
    ("Xpeng",       "小鹏汽车"),
    ("LiAuto",      "理想汽车"),
]

CITY_CODE = "100010000"      # 全国
PAGE_DELAY = 4               # 翻页后等池
CARD_DELAY = 1.5             # 点卡片后等详情加载
MAX_CONSEC_EMPTY = 4         # 连续检测不到卡片停止
MAX_PAGES = 300              # 单公司最多翻300页


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def wait_for_user_login(page):
    """弹窗 — 用户扫码登录 Boss 直聘。"""
    page.get(f"https://www.zhipin.com/web/geek/job?city={CITY_CODE}")
    time.sleep(3)
    ctypes.windll.user32.MessageBoxW(
        0,
        "请在打开的浏览器里：\n"
        "1. 用 Boss 直聘 App 扫码登录\n"
        "2. 完成滑块 / 验证码\n"
        "3. 确认职位列表正常展示\n\n"
        "完成后点击 [确定] 开始自动抓取",
        "Boss 直聘 — 请先登录",
        0x00001000 | 0x00000040,
    )
    log("用户已确认登录，开始抓取...")


def find_cards(page):
    """在当前页面检测职位卡片列表。"""
    selectors = [
        ".job-card-wrapper",
        ".job-card",
        ".job-card-body",
    ]
    for sel in selectors:
        try:
            cards = page.eles(sel, timeout=3)
            if cards:
                return cards
        except:
            continue

    # 兜底：找到 job-list-box 下的 li
    try:
        box = page.ele(".job-list-box", timeout=2)
        if box:
            lis = box.eles("tag:li")
            if lis:
                return lis
    except:
        pass
    return []


def extract_detail(page):
    """从右侧详情面板提取职位信息。返回 dict 或 None。"""
    fields = {}

    # 标题
    for sel in [".name", ".job-name", ".position-title", "h1"]:
        el = page.ele(sel, timeout=1)
        if el and el.text.strip():
            fields["title"] = el.text.strip()
            break
    if "title" not in fields:
        return None

    # 公司
    for sel in [".company-info", ".company-name"]:
        el = page.ele(sel, timeout=1)
        if el and el.text.strip():
            fields["company"] = el.text.strip()[:120]
            break

    # 薪资
    for sel in [".salary", ".job-salary"]:
        el = page.ele(sel, timeout=1)
        if el and el.text.strip():
            fields["salary"] = el.text.strip()
            break

    # 经验/学历标签
    tag_els = page.eles(".job-tags tag:span", timeout=0.8)
    tag_texts = [t.text.strip() for t in tag_els if t.text.strip()]
    fields["tags"] = tag_texts
    # 城市通常在第一项
    if tag_texts:
        fields["city"] = tag_texts[0].split("·")[0]
    else:
        fields["city"] = ""

    # JD 正文
    for sel in [".job-detail-section", ".detail-content", ".job-desc"]:
        el = page.ele(sel, timeout=2)
        if el and el.text.strip():
            fields["jd_text"] = el.text.strip()[:6000]
            break
    if "jd_text" not in fields:
        fields["jd_text"] = ""

    return fields


def scrape_company(page, eng_name, keyword):
    """搜索并抓取一家公司的所有页面。"""
    outpath = OUT_DIR / f"{eng_name}.jsonl"
    log(f"\n{'─'*50}")
    log(f"开始抓取: {keyword}")
    log(f"{'─'*50}")

    url = f"https://www.zhipin.com/web/geek/job?query={keyword}&city={CITY_CODE}"
    page.get(url)
    time.sleep(4)

    records = []
    seen = set()
    page_num = 1
    empty_streak = 0

    while empty_streak < MAX_CONSEC_EMPTY and page_num <= MAX_PAGES:
        log(f"  第 {page_num} 页 ...")
        cards = find_cards(page)

        if not cards:
            empty_streak += 1
            log(f"    空页 ×{empty_streak}")
            if empty_streak >= MAX_CONSEC_EMPTY:
                break
            page_num += 1
            try:
                click_next(page)
            except:
                pass
            continue
        empty_streak = 0

        for i, card in enumerate(cards):
            try:
                card.scroll_to_see()
                time.sleep(0.2)
                card.click()
                time.sleep(CARD_DELAY)

                job = extract_detail(page)
                if not job:
                    continue

                key = job["title"] + (job.get("company", "") or "")[:30]
                if key in seen:
                    continue
                seen.add(key)

                job["search_query"] = keyword
                job["page"] = page_num
                job["crawl_ts"] = datetime.now(timezone.utc).isoformat()
                records.append(job)
            except:
                pass

        log(f"    本页成功 {len(records)} 条累计")

        # 翻页
        ok = click_next(page)
        if not ok:
            log("    已达末页")
            break
        page_num += 1

    # 保存
    with open(outpath, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    log(f"\n✓ {keyword}: 保存 {len(records)} 条 -> {outpath}")
    return len(records)


def click_next(page):
    """点击下一页，返回 True 成功，False 末页。"""
    for sel in [".ui-icon-arrow-right", ".options-pages a:last-of-type"]:
        el = page.ele(sel, timeout=1.5)
        if not el:
            continue
        parent = el.parent()
        cls = (parent.attr("class") or "") if parent else ""
        if "disabled" in cls or "disable" in cls.lower():
            return False
        try:
            el.click()
            time.sleep(PAGE_DELAY)
            return True
        except:
            return False
    return False


def main():
    log("启动 Boss 直聘浏览器 ...")
    page = ChromiumPage()
    wait_for_user_login(page)

    # 跳过已完成的企业（支持断点续抓）
    grand_total = 0
    for eng, kw in COMPANIES:
        outpath = OUT_DIR / f"{eng}.jsonl"
        if outpath.exists() and outpath.stat().st_size > 100:
            lines = outpath.read_text(encoding="utf-8").strip().split("\n")
            cnt = len([l for l in lines if l.strip()])
            log(f"  [跳过] {kw} — 已有 {cnt} 条")
            grand_total += cnt
            continue

        try:
            cnt = scrape_company(page, eng, kw)
            grand_total += cnt
        except Exception as e:
            log(f"✗ [{kw}] 出错: {e}")
            import traceback
            traceback.print_exc()
            continue

    log(f"\n{'='*60}")
    log(f"抓取完成！总共 {grand_total} 条招聘职位")
    log(f"输出目录: {OUT_DIR}")
    log(f"{'='*60}")

    # 汇总
    summary = []
    for f in sorted(OUT_DIR.glob("*.jsonl")):
        lines = f.read_text(encoding="utf-8").strip().split("\n")
        cnt = len([l for l in lines if l.strip()])
        summary.append((f.stem, cnt))

    print("\n各企业汇总:")
    for name, cnt in summary:
        print(f"  {name:20s} {cnt:5d} 条")
    print(f"  {'─'*30}")
    print(f"  {'合计':20s} {grand_total:5d} 条")

    log("\n浏览器保持打开，手动关闭即可。")


if __name__ == "__main__":
    main()