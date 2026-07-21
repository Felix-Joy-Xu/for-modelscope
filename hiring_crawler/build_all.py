"""One-shot builder: generates the complete hiring crawler framework."""
import os

BASE = r"C:\Users\22735\Desktop\文献\hiring_crawler"
os.makedirs(os.path.join(BASE, "output"), exist_ok=True)

# ============================================================
# 1. config.py
# ============================================================
with open(os.path.join(BASE, "config.py"), "w", encoding="utf-8") as f:
    f.write("""\"\"\"Unified config - Chinese tech company programmer job listings.\"\"\"
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"

TECH_FILTER = [
    "backend", "frontend", "algorithm", "AI", "machine learning",
    "deep learning", "NLP", "LLM", "AIGC", "Java", "Python", "C++", "Go",
    "Golang", "Rust", "JavaScript", "TypeScript", "developer", "engineer",
    "architect", "big data", "data warehouse", "testing", "QA", "DevOps",
    "SRE", "Kubernetes", "security", "embedded", "Android", "iOS",
    "game", "Unity", "blockchain", "autonomous", "perception", "SLAM",
    "chip", "IC", "FPGA", "cloud", "distributed", "microservices",
    "recommendation", "advertising", "quantitative",
    "intern", "campus", "graduate",
]

NON_TECH = [
    "sales", "customer service", "admin", "HR", "finance", "legal",
    "marketing", "editor", "UI", "UX", "product manager",
    "business", "procurement", "logistics",
]

# Companies with public REST APIs (no browser needed)
DIRECT_API = {
    "tencent_social": {
        "name": "Tencent-Social",
        "url": "https://careers.tencent.com/tencentcareer/api/post/QueryByKeyword",
        "method": "POST",
        "payload": {
            "keyword": "tech", "pageIndex": 1, "pageSize": 100,
            "language": "zh-cn", "area": "cn",
        },
        "headers": {
            "Referer": "https://careers.tencent.com/",
            "Content-Type": "application/json",
        },
        "data_path": "Data.Posts",
        "job_id_field": "PostId",
        "title_field": "RecruitPostName",
        "location_field": "LocationName",
        "department_field": "BGName",
        "jd_fields": ["Responsibility", "Requirement"],
    },
    "meituan_social": {
        "name": "Meituan-Social",
        "url": "https://zhaopin.meituan.com/api/qrcode/positions",
        "method": "GET",
        "params_template": {"pageNo": 1, "pageSize": 50, "lang": "zh"},
        "data_path": "data.list",
        "job_id_field": "id",
        "title_field": "title",
        "location_field": "workCity",
        "department_field": "deptName",
        "jd_fields": ["jd"],
    },
    "kuaishou_social": {
        "name": "Kuaishou-Social",
        "url": "https://zhaopin.kuaishou.cn/api/recruit/portal/job/list",
        "method": "POST",
        "payload": {
            "pageNum": 1, "pageSize": 50, "keyword": "tech",
        },
        "headers": {
            "Referer": "https://zhaopin.kuaishou.cn/",
            "Content-Type": "application/json",
        },
        "data_path": "data.list",
        "job_id_field": "id",
        "title_field": "jobTitle",
        "location_field": "workPlaceName",
        "department_field": "deptName",
        "jd_fields": ["jobDescription"],
    },
}

# Companies to crawl via Boss Zhipin (browser automation)
BOSS_QUERIES = [
    ("Bytedance", "字节跳动"),
    ("Pinduoduo", "拼多多"),
    ("DJI", "大疆"),
    ("DeepSeek", "深度求索"),
    ("miHoYo", "米哈游"),
    ("AntGroup", "蚂蚁集团"),
    ("BYD", "比亚迪"),
    ("NIO", "蔚来"),
    ("Xpeng", "小鹏"),
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
""")

# ============================================================
# 2. base.py  -  unified crawler base class
# ============================================================
with open(os.path.join(BASE, "base.py"), "w", encoding="utf-8") as f:
    f.write('''"""Base crawler class with pagination, dedup, tech-filter, JSONL output."""
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

class BaseCrawler:
    def __init__(self, name, output_subdir=""):
        self.name = name
        out = Path(__file__).parent / "output" / output_subdir
        out.mkdir(parents=True, exist_ok=True)
        self.out_file = out / f"{name}.jsonl"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        self.seen_ids = set()
        self.total = 0

    # ---- helpers ----
    @staticmethod
    def deep_get(d, path, default=None):
        """drill into nested dict via dotted path e.g. 'Data.Posts'."""
        for key in path.split("."):
            if isinstance(d, dict):
                d = d.get(key, {})
            else:
                return default
        return d if d != {} else default

    def is_tech_job(self, title, jd_text):
        """Naive tech-vs-non-tech filter using keyword lookup."""
        text = f"{title} {jd_text}".lower()
        has_tech = any(kw.lower() in text for kw in [
            "backend", "frontend", "algorithm", "ai", "machine learning",
            "deep learning", "nlp", "llm", "aigc", "java", "python", "c++",
            "go", "golang", "rust", "javascript", "typescript",
            "developer", "engineer", "architect", "研发", "技术",
            "big data", "data warehouse", "testing", "qa", "devops",
            "sre", "kubernetes", "security", "embedded", "android", "ios",
            "game", "unity", "blockchain", "autonomous", "perception",
            "slam", "chip", "ic", "fpga", "cloud", "distributed",
            "microservices", "recommendation", "advertising", "quant",
            "intern", "campus", "graduate", "开发", "算法",
            "测试", "运维", "安全", "数据", "前端", "后端",
        ])
        has_nontech = any(kw.lower() in text for kw in [
            "sales", "customer service", "admin", "hr", "finance",
            "legal", "marketing", "editor", "product manager",
            "business", "procurement", "logistics", "销售", "客服",
            "行政", "人力", "财务", "法务", "市场", "编辑",
            "产品经理", "商务", "采购", "物流",
        ])
        return has_tech and not has_nontech

    # ---- pagination loop ----
    def run_pagination(self, fetch_fn, parse_fn, start_page=1, delay=2.0):
        """Generic page-by-page crawl."""
        page = start_page
        while True:
            try:
                raw = fetch_fn(page)
                if raw is None:
                    print(f"  [{self.name}] page={page}: fetch returned None, stopping.")
                    break
                records = parse_fn(raw)
                new = [r for r in records if r["job_id"] not in self.seen_ids]
                if not new:
                    print(f"  [{self.name}] page={page}: no new IDs, stopping.")
                    break
                for r in new:
                    self.seen_ids.add(r["job_id"])
                self._save(new)
                print(f"  [{self.name}] page={page}: +{len(new)}, total={self.total}")
                page += 1
                time.sleep(delay)
            except Exception as e:
                print(f"  [{self.name}] page={page} error: {e}")
                break
        return self.total

    def _save(self, records):
        with open(self.out_file, "a", encoding="utf-8") as f:
            for r in records:
                r["crawl_ts"] = datetime.now(timezone.utc).isoformat()
                f.write(json.dumps(r, ensure_ascii=False) + "\\n")
                self.total += 1

    # ---- result summary ----
    def summary(self):
        print(f"\\n[{self.name}] DONE.  Total unique jobs: {self.total}")
        print(f"  Output: {self.out_file}")
''')

# ============================================================
# 3. direct_api_crawlers.py  -  crawlers for Tencent / Meituan / Kuaishou
# ============================================================
with open(os.path.join(BASE, "direct_api_crawlers.py"), "w", encoding="utf-8") as f:
    f.write('''"""Crawlers that hit public REST APIs directly (no browser needed)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from base import BaseCrawler
from config import DIRECT_API


class DirectAPICrawler(BaseCrawler):
    """Generic crawler driven by a config dict."""

    def __init__(self, cfg_key):
        cfg = DIRECT_API[cfg_key]
        super().__init__(cfg["name"])
        self.cfg = cfg
        self.session.headers.update(cfg.get("headers", {}))

    def fetch_page(self, page):
        cfg = self.cfg
        if cfg["method"] == "GET":
            params = dict(cfg.get("params_template", {}))
            params["pageNo"] = page
            resp = self.session.get(cfg["url"], params=params, timeout=15)
        else:
            payload = dict(cfg["payload"])
            payload["pageIndex"] = page
            resp = self.session.post(cfg["url"], json=payload, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return self.deep_get(data, cfg["data_path"])

    def parse(self, job_list):
        cfg = self.cfg
        records = []
        for item in (job_list or []):
            jid = str(item.get(cfg["job_id_field"], ""))
            title = item.get(cfg["title_field"], "") or ""
            jd_parts = []
            for fld in cfg["jd_fields"]:
                v = item.get(fld, "")
                if v:
                    jd_parts.append(str(v))
            jd_text = "\\n".join(jd_parts)
            if not self.is_tech_job(title, jd_text):
                continue
            records.append({
                "job_id": jid,
                "title": title,
                "company": cfg["name"],
                "location": str(item.get(cfg["location_field"], "")),
                "department": str(item.get(cfg["department_field"], "")),
                "jd_text": jd_text,
                "source": "direct_api",
            })
        return records

    def run(self):
        print(f"\\n{'='*40}")
        print(f"  Crawling {self.cfg['name']} ...")
        print(f"{'='*40}")
        self.run_pagination(self.fetch_page, self.parse)
        self.summary()


def crawl_all_direct():
    """Run all direct-API crawlers."""
    for key in DIRECT_API:
        try:
            c = DirectAPICrawler(key)
            c.run()
        except Exception as e:
            print(f"[{key}] FAILED: {e}")


if __name__ == "__main__":
    crawl_all_direct()
''')

# ============================================================
# 4. boss_zhipin_multi.py  -  Boss crawler for many companies
# ============================================================
with open(os.path.join(BASE, "boss_zhipin_multi.py"), "w", encoding="utf-8") as f:
    f.write(r'''"""Boss Zhipin multi-company crawler using DrissionPage (browser automation).

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
''')

# ============================================================
# 5. run_all.py  -  master launcher
# ============================================================
with open(os.path.join(BASE, "run_all.py"), "w", encoding="utf-8") as f:
    f.write('''"""Master launcher - runs all crawlers sequentially.

Usage:
    # Crawl direct-API companies only (fast, no browser needed):
    python run_all.py --direct

    # Crawl Boss Zhipin companies only (needs manual login):
    python run_all.py --boss

    # Crawl everything:
    python run_all.py --all
"""
import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).parent


def run_script(rel_path):
    p = HERE / rel_path
    print(f"\\n{'#'*60}")
    print(f"# Running: {p.name}")
    print(f"{'#'*60}")
    subprocess.run([sys.executable, str(p)], cwd=str(HERE))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\\nOptions: --direct  --boss  --all")
        return

    mode = sys.argv[1]

    if mode in ("--direct", "--all"):
        run_script("direct_api_crawlers.py")

    if mode in ("--boss", "--all"):
        print("\\n[INFO] Boss Zhipin crawler requires manual login.")
        print("[INFO] A dialog will pop up - follow the instructions.")
        run_script("boss_zhipin_multi.py")

    print("\\nAll crawlers finished.")


if __name__ == "__main__":
    main()
''')

print("=" * 50)
print("  hiring_crawler framework built successfully!")
print("=" * 50)
print(f"  Location: {BASE}")
print()
print("  Files created:")
for f in sorted(os.listdir(BASE)):
    fp = os.path.join(BASE, f)
    if os.path.isfile(fp) and f.endswith(".py"):
        size = os.path.getsize(fp)
        print(f"    {f}  ({size:,} bytes)")
print()
print("  Quick start:")
print(f"    cd {BASE}")
print("    python run_all.py --direct    # fast API crawlers")
print("    python run_all.py --boss      # Boss Zhipin (browser)")
print("    python run_all.py --all       # everything")