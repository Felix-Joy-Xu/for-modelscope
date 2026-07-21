"""Unified config - Chinese tech company programmer job listings."""
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
