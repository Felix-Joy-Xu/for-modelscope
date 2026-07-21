import os as _os
try:
    from _secrets import MODELSCOPE_TOKEN, MODELSCOPE_TOKENS
except ImportError:
    MODELSCOPE_TOKEN = _os.environ.get("MODELSCOPE_TOKEN", "")
    MODELSCOPE_TOKENS = [t for t in _os.environ.get("MODELSCOPE_TOKENS", "").split(",") if t]

"""测试新 API list_repos 多种 repo_type（含 Studio/Skill/MCP）"""
import os, json
os.environ["MODELSCOPE_API_TOKEN"] = MODELSCOPE_TOKEN
from modelscope.hub.api import HubApi
from modelscope_hub.types import RepoType
api = HubApi()

for rt in [RepoType.STUDIO, RepoType.SKILL, RepoType.MCP, RepoType.MODEL, RepoType.DATASET]:
    try:
        r = api.list_repos(repo_type=rt, page_size=5, page_number=1)
        tc = r.total_count if hasattr(r, "total_count") else "?"
        print(f"{rt}: items={len(r.items)} total={tc}")
        if r.items:
            d = r.items[0].to_dict() if hasattr(r.items[0], "to_dict") else r.items[0]
            print(f"  first keys: {list(d.keys())[:12]}")
    except Exception as e:
        print(f"{rt}: ERR {str(e)[:80]}")

# 试 MODEL 大集合
print("\n=== MODEL 全集分页测试 ===")
all_seen = set()
total_count = None
for p in [1, 10, 50, 100]:
    r = api.list_repos(repo_type=RepoType.MODEL, page_size=50, page_number=p)
    if total_count is None:
        total_count = r.total_count
    items_seen = sum(1 for it in r.items if it.id not in all_seen)
    for it in r.items:
        all_seen.add(it.id)
    print(f"p{p}: items={len(r.items)} new={items_seen}")

print(f"\nMODEL 全集 total_count: {total_count}")
print(f"3000/50 = 60页上限")

# DATASET 全集
print("\n=== DATASET 全集分页测试 ===")
ds_total = None
for p in [1, 10, 50, 60]:
    r = api.list_repos(repo_type=RepoType.DATASET, page_size=50, page_number=p)
    if ds_total is None:
        ds_total = r.total_count
    print(f"p{p}: items={len(r.items)} has_next={r.has_next}")
print(f"DATASET 全集 total_count: {ds_total}")