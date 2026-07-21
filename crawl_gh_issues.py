#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集 GitHub modelscope/modelscope 仓库的 Discussions + Issues
========================================================
- Discussions: REST API (没有官方 endpoint，用 GraphQL)
- Issues: /repos/{owner}/{repo}/issues REST API
- 同时保存评论

输出:
  modelscope_output/github_discussions/
    issues_all.json
    discussions_all.json
    comments_all.json
"""

import os, json, time, requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
OUT_DIR = os.path.join(OUTPUT_DIR, "github_discussions")
os.makedirs(OUT_DIR, exist_ok=True)

OWNER = "modelscope"
REPO = "modelscope"
TOKEN = os.environ.get("GITHUB_TOKEN", "")  # 如果有就用

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/vnd.github+json",
})
if TOKEN:
    session.headers["Authorization"] = f"Bearer {TOKEN}"
    print("使用 GitHub Token")
else:
    print("无 Token, 用未认证模式 (60 req/hr)")

# ============================================================================
# 1. 采集 Issues（含评论）
# ============================================================================

print("\n" + "="*60)
print("1. 采集 Issues")
print("="*60)

all_issues = []
page = 1
cursor = None  # 用 cursor 分页
while True:
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/issues"
    params = {"state": "all", "per_page": 100, "direction": "desc"}
    if cursor:
        params["after"] = cursor
    else:
        params["page"] = page
    r = session.get(url, params=params, timeout=15)
    if r.status_code != 200:
        # 试试 cursor 分页
        if r.status_code == 422 and not cursor:
            # 改用 cursor: from last item
            if all_issues:
                cursor = f"cursor:{all_issues[-1]['id']}"
                page += 1
                continue
        print(f"  [page {page}] {r.status_code}: {r.text[:80]}")
        break
    issues = r.json()
    if not issues:
        print(f"  page {page} empty, stop")
        break

    for issue in issues:
        if "pull_request" in issue:
            continue
        all_issues.append({
            "id": issue["id"],
            "number": issue["number"],
            "title": issue["title"],
            "body": issue.get("body", "") or "",
            "state": issue["state"],
            "created_at": issue["created_at"],
            "updated_at": issue["updated_at"],
            "comments_count": issue["comments"],
            "comments_url": issue["comments_url"],
            "user": issue["user"]["login"],
            "labels": [l["name"] for l in issue.get("labels", [])],
            "url": issue["html_url"],
        })

    print(f"  page {page}: {len([i for i in issues if 'pull_request' not in i])} issues (累计 {len(all_issues)})")
    rem = r.headers.get("X-RateLimit-Remaining")
    if rem and int(rem) < 10:
        print(f"  rate limit: {rem}")
        break
    if len(issues) < 100:
        break
    # cursor: 用上页最后一条 id
    cursor = f"cursor:{issues[-1]['id']}"
    page += 1
    time.sleep(1)

print(f"\n  Total issues: {len(all_issues)}")

# ============================================================================
# 2. 采集所有评论
# ============================================================================

print("\n" + "="*60)
print("2. 采集评论")
print("="*60)

all_comments = []
for i, issue in enumerate(all_issues):
    if issue["comments_count"] == 0:
        continue
    url = issue["comments_url"]
    r = session.get(url, timeout=15)
    if r.status_code != 200:
        continue
    for c in r.json():
        all_comments.append({
            "issue_number": issue["number"],
            "comment_id": c["id"],
            "body": c.get("body", ""),
            "user": c["user"]["login"],
            "created_at": c["created_at"],
            "url": c["html_url"],
        })
    if (i + 1) % 50 == 0:
        print(f"  processed {i+1}/{len(all_issues)} issues, {len(all_comments)} comments")
    time.sleep(0.5)  # 礼貌延迟

print(f"\n  Total comments: {len(all_comments)}")

# ============================================================================
# 3. 采集 Discussions (使用 GraphQL - 需 token)
# ============================================================================

print("\n" + "="*60)
print("3. 采集 Discussions (需 GitHub Token)")
print("="*60)

all_discussions = []
if TOKEN:
    # GraphQL query 找含 discussions 的
    query = """
    query {
      repository(owner: "%s", name: "%s") {
        discussions(first: 100) {
          nodes {
            number title bodyText url
            createdAt updatedAt
            author { login }
            labels(first: 10) { nodes { name } }
            comments(first: 50) { 
              nodes { bodyText author { login } createdAt url }
            }
          }
        }
      }
    }""" % (OWNER, REPO)
    r = session.post("https://api.github.com/graphql",
                      json={"query": query}, timeout=30)
    if r.status_code == 200:
        data = r.json()
        discussions = data.get("data", {}).get("repository", {}).get("discussions", {}).get("nodes", [])
        for d in discussions:
            d_comments = d.get("comments", {}).get("nodes", [])
            all_discussions.append({
                "number": d["number"],
                "title": d["title"],
                "body": d.get("bodyText", ""),
                "url": d["url"],
                "created_at": d["createdAt"],
                "updated_at": d["updatedAt"],
                "author": (d.get("author") or {}).get("login"),
                "labels": [l["name"] for l in d.get("labels", {}).get("nodes", [])],
                "comments_count": len(d_comments),
                "comments": [{"body": c["bodyText"], "user": (c.get("author") or {}).get("login"),
                              "created_at": c["createdAt"]} for c in d_comments],
            })
        print(f"  Discussions: {len(all_discussions)}")
    else:
        print(f"  [{r.status_code}] {r.text[:200]}")
else:
    print("  跳过（需要 GitHub Token 设置 env GITHUB_TOKEN）")

# ============================================================================
# 保存
# ============================================================================

print("\n" + "="*60)
print("保存")
print("="*60)

with open(os.path.join(OUT_DIR, "issues_all.json"), "w", encoding="utf-8") as f:
    json.dump(all_issues, f, ensure_ascii=False, indent=2)
print(f"  issues_all.json: {len(all_issues)} 条")

with open(os.path.join(OUT_DIR, "comments_all.json"), "w", encoding="utf-8") as f:
    json.dump(all_comments, f, ensure_ascii=False, indent=2)
print(f"  comments_all.json: {len(all_comments)} 条")

with open(os.path.join(OUT_DIR, "discussions_all.json"), "w", encoding="utf-8") as f:
    json.dump(all_discussions, f, ensure_ascii=False, indent=2)
print(f"  discussions_all.json: {len(all_discussions)} 条")

# 统计
total_chars = sum(len(i["body"] or "") for i in all_issues)
total_chars += sum(len(c["body"] or "") for c in all_comments)
total_chars += sum(len(d.get("body", "") or "") for d in all_discussions)
total_chars += sum(len(c["body"] or "") for d in all_discussions for c in d.get("comments", []))
print(f"\n总语料 chars: {total_chars:,}")