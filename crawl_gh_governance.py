#!/usr/bin/env python3
"""补 GitHub 上 modelscope/modelscope 仓库治理文件全文"""
import os, json, requests, time

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
GH_DIR = os.path.join(OUTPUT_DIR, "github_governance")
os.makedirs(GH_DIR, exist_ok=True)

# 1. 仓库治理文件
GH_FILES = {
    "LICENSE": "LICENSE",
    "CODE_OF_CONDUCT": "CODE_OF_CONDUCT.md",
    "README": "README.md",
    "bug_report": ".github/ISSUE_TEMPLATE/bug_report.md",
    "feature_request": ".github/ISSUE_TEMPLATE/feature_request.md",
    "question_template": ".github/ISSUE_TEMPLATE/question.md",
}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

print("=== GitHub 仓库治理文件 ===")
saved = []
for name, path in GH_FILES.items():
    url = f"https://raw.githubusercontent.com/modelscope/modelscope/master/{path}"
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            filepath = os.path.join(GH_DIR, f"gh_{name}.txt")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# GitHub file: {path}\n# URL: {url}\n# Size: {len(r.text)} chars\n{'='*80}\n\n{r.text}")
            print(f"  [OK] {name}: {len(r.text)} chars -> gh_{name}.txt")
            saved.append({"name": name, "path": path, "length": len(r.text), "chars_len": len(r.text)})
        else:
            print(f"  [{r.status_code}] {name}")
    except Exception as e:
        print(f"  [ERR] {name}: {str(e)[:60]}")
    time.sleep(0.3)

# 2. 仓库元数据
print("\n=== GitHub 仓库元数据 ===")
gh_meta = {}
for api_url in [
    "https://api.github.com/repos/modelscope/modelscope",
    "https://api.github.com/orgs/modelscope",
]:
    try:
        r = session.get(api_url, timeout=15)
        if r.status_code == 200:
            d = r.json()
            gh_meta[api_url.split("repos/")[1] if "repos" in api_url else "org"] = {
                "name": d.get("name") or d.get("full_name"),
                "description": d.get("description"),
                "stargazers_count": d.get("stargazers_count"),
                "forks_count": d.get("forks_count"),
                "open_issues": d.get("open_issues_count"),
                "license": (d.get("license") or {}).get("name") if isinstance(d.get("license"), dict) else None,
                "topics": d.get("topics"),
                "created_at": d.get("created_at"),
                "updated_at": (d.get("updated_at") or d.get("pushed_at")),
                "public_repos": d.get("public_repos", 0),
                "blog": d.get("blog"),
                "twitter": d.get("twitter_username"),
                "type": d.get("type"),
            }
            print(f"  OK: {gh_meta[list(gh_meta.keys())[-1]]['name']}")
    except Exception as e:
        print(f"  ERR: {str(e)[:60]}")

# 3. 列出 organization 下所有仓库
print("\n=== modelscope org 的仓库列表 ===")
page = 1
all_repos = []
while True:
    try:
        r = session.get(f"https://api.github.com/orgs/modelscope/repos?per_page=100&page={page}", timeout=15)
        if r.status_code != 200:
            break
        repos = r.json()
        if not repos:
            break
        for repo in repos:
            all_repos.append({
                "name": repo["name"],
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "license": (repo.get("license") or {}).get("name") if repo.get("license") else None,
                "language": repo.get("language"),
                "description": repo.get("description"),
                "open_issues": repo["open_issues_count"],
                "created_at": repo["created_at"],
                "updated_at": repo.get("updated_at"),
            })
        if len(repos) < 100:
            break
        page += 1
        time.sleep(1)
    except Exception as e:
        print(f"  ERR: {str(e)[:60]}")
        break

print(f"  共 {len(all_repos)} 个仓库")

# 保存
with open(os.path.join(GH_DIR, "gh_governance_meta.json"), "w", encoding="utf-8") as f:
    json.dump({"files": saved, "meta": gh_meta, "repos": all_repos}, f, ensure_ascii=False, indent=2)

print(f"\n保存:")
print(f"  gh_*.txt: 治理文件全文")
print(f"  gh_governance_meta.json: 仓库元数据 + 全仓库列表")