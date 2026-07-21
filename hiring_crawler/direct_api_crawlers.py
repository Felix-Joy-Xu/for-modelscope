"""Crawlers that hit public REST APIs directly (no browser needed)."""
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
            jd_text = "\n".join(jd_parts)
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
        print(f"\n{'='*40}")
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
