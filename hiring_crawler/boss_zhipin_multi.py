"""Boss Zhipin multi-company crawler using DrissionPage (browser automation).

Usage:
    python boss_zhipin_multi.py

Workflow:
    1. Opens Boss Zhipin search page
    2. Pops a dialog - user manually logs in & solves captcha
    3. Iterates through each company keyword, collects tech jobs
    4. Saves each company's results to separate JSONL files
"""
import json
import time
import ctypes
from pathlib import Path
from datetime import datetime, timezone
from DrissionPage import ChromiumPage

OUT_DIR = Path(__file__).parent / "output" / "boss_zhipin"
OUT_DIR.mkdir(parents=True, exist_ok=True)

COMPANIES = [
    ("Bytedance", "字节跳动"),
    ("Pinduoduo", "拼多多"),
    ("DJI", "大疆"),
    ("DeepSeek", "深度求索"),
    ("miHoYo", "米哈游"),
    ("AntGroup", "蚂蚁集团"),
    ("BYD", "比亚迪"),
    ("NIO", "蔚来"),
    ("Xpeng", "小鹏汽车"),
    ("LiAuto", "理想汽车"),
    ("Huawei", "华为"),
    ("Baidu", "百度"),
    ("Didi", "滴滴"),
    ("Bilibili", "哔哩哔哩"),
    ("Shopee", "Shopee"),
    ("Zoom", "Zoom"),
    ("Xiaohongshu", "小红书"),
    ("JD", "京东"),
    ("NetEase", "网易"),
    ("Xiaomi", "小米"),
]

TECH_KEYWORDS = [
    "后端", "前端", "算法", "AI", "大模型", "机器学习", "深度学习",
    "NLP", "CV", "LLM", "AIGC", "Java", "Python", "C++", "Go",
    "开发", "工程师", "架构师", "数据", "大数据", "测试", "运维",
    "安全", "嵌入式", "Android", "iOS", "游戏", "自动驾驶",
    "芯片", "云计算", "分布式",
]


def is_tech(title, jd):
    text = f"{title} {jd}"
    has_t = any(kw in text for kw in TECH_KEYWORDS)
    no_t = any(kw in text for kw in [
        "销售", "客服", "行政", "HR", "财务", "法务", "市场",
        "编辑", "产品经理", "商务", "采购", "司机",
    ])
    return has_t and not no_t


def scrape_boss_for_company(page, eng_name, cn_keyword):
    print(f"\n{'='*50}")
    print(f"  Searching: {cn_keyword} ({eng_name})")
    print(f"{'='*50}")

    url = (
        f"https://www.zhipin.com/web/geek/job"
        f"?query={cn_keyword}&city=100010000"
    )
    page.get(url)
    time.sleep(3)

    jobs = []
    page_num = 1

    while True:
        print(f"  Page {page_num} ...")
        try:
            cards = page.eles(".job-card-wrapper", timeout=3)
            if not cards:
                ul = page.ele(".job-list-box", timeout=2)
                if ul:
                    cards = ul.eles("tag:li")
        except:
            cards = []

        if not cards:
            print("  No job cards found, moving on.")
            break

        for card in cards:
            try:
                card.click()
                time.sleep(1.5)

                title_el = (page.ele(".name", timeout=2) or
                            page.ele(".job-name", timeout=2))
                title = title_el.text.strip() if title_el else ""

                comp_el = (page.ele(".company-info", timeout=1) or
                           page.ele(".company-name", timeout=1))
                company = comp_el.text.strip() if comp_el else ""

                jd_el = (page.ele(".job-detail-section", timeout=2) or
                         page.ele(".detail-content", timeout=2))
                jd_text = jd_el.text.strip() if jd_el else ""

                if jd_text and is_tech(title, jd_text):
                    jobs.append({
                        "title": title,
                        "company": company,
                        "jd_text": jd_text,
                        "search_keyword": cn_keyword,
                        "crawl_ts": datetime.now(timezone.utc).isoformat(),
                    })
            except:
                pass

        # next page
        try:
            next_btn = page.ele(".ui-icon-arrow-right", timeout=2)
            if next_btn:
                p = next_btn.parent()
                if p and "disabled" in (p.attr("class") or ""):
                    break
                next_btn.click()
                page_num += 1
                time.sleep(3)
            else:
                break
        except:
            break

    # save
    out = OUT_DIR / f"{eng_name}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")
    print(f"  -> Saved {len(jobs)} jobs to {out.name}")
    return len(jobs)


def main():
    page = ChromiumPage()
    page.get("https://www.zhipin.com/web/geek/job?query=AI&city=100010000")

    ctypes.windll.user32.MessageBoxW(
        0,
        "Please manually:\n"
        "1. Scan QR code to login\n"
        "2. Solve any captcha/slider\n"
        "3. Wait until job list renders\n\n"
        "Click OK when ready!",
        "Boss Zhipin - Login Required",
        0x00001000 | 0x00000040,
    )

    total_all = 0
    for eng, cn in COMPANIES:
        try:
            cnt = scrape_boss_for_company(page, eng, cn)
            total_all += cnt
        except Exception as e:
            print(f"  [{cn}] ERROR: {e}")
            continue

    print(f"\n{'='*50}")
    print(f"  ALL DONE. Total tech jobs collected: {total_all}")
    print(f"  Output: {OUT_DIR}")
    print(f"{'='*50}")

    print("\nBrowser kept alive. Close manually when done.")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
