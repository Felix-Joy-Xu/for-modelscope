"""Base crawler class with pagination, dedup, tech-filter, JSONL output."""
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
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                self.total += 1

    # ---- result summary ----
    def summary(self):
        print(f"\n[{self.name}] DONE.  Total unique jobs: {self.total}")
        print(f"  Output: {self.out_file}")
