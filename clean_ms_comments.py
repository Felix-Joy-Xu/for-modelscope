# -*- coding: utf-8 -*-
"""清洗魔搭评论汇总数据：去重 + 解析 summary 字段 → 结构化 CSV。

输入: modelscope_output/ms_comments_all.jsonl（含重复与错误记录）
输出: 02-原始数据/各平台原始数据/modelscope_comments_summary.csv
"""

import csv
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "modelscope_output", "ms_comments_all.jsonl")
DST = r"D:\国际比较政治经济学\02-原始数据\各平台原始数据\modelscope_comments_summary.csv"


def parse_top3(raw):
    """Top3 是 JSON 字符串，如 '["体验效果不佳"," 愿意推荐"]'，解析并去空白。"""
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if isinstance(items, list):
            return [str(x).strip() for x in items if str(x).strip()]
    except Exception:
        pass
    return []


def main():
    best = {}  # model_id -> record（成功的优先；同状态取 crawled_at 最新）
    n_total = n_err = 0
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_total += 1
            r = json.loads(line)
            mid = r.get("model_id", "")
            if not mid:
                continue
            ok = bool(r.get("api_intercepts")) and r.get("status") != "error"
            if not ok:
                n_err += 1
            prev = best.get(mid)
            if prev is None:
                best[mid] = r
            else:
                prev_ok = bool(prev.get("api_intercepts")) and prev.get("status") != "error"
                if ok and not prev_ok:
                    best[mid] = r
                elif ok == prev_ok and (r.get("crawled_at") or 0) > (prev.get("crawled_at") or 0):
                    best[mid] = r

    rows = []
    for mid, r in best.items():
        data = {}
        for it in r.get("api_intercepts") or []:
            d = (it.get("data") or {}).get("Data")
            if isinstance(d, dict) and d:
                data = d
                break
        top3 = parse_top3(data.get("Top3"))
        rows.append({
            "model_id": mid,
            "status": "ok" if data else "error",
            "avg_score": data.get("AvgScore"),
            "comment_count": data.get("Count"),
            "total_count": data.get("TotalCount"),
            "discussion_count": data.get("DiscussionCount"),
            "issue_open": data.get("IssueOpenCount"),
            "issue_closed": data.get("IssueClosedCount"),
            "pr_open": data.get("PrOpenCount"),
            "pr_closed": data.get("PrClosedCount"),
            "visible": data.get("Visible"),
            "top3_1": top3[0] if len(top3) > 0 else "",
            "top3_2": top3[1] if len(top3) > 1 else "",
            "top3_3": top3[2] if len(top3) > 2 else "",
            "error": r.get("error", "") if not data else "",
            "crawled_at": r.get("crawled_at"),
        })

    rows.sort(key=lambda x: (x["comment_count"] or 0), reverse=True)

    fields = ["model_id", "status", "avg_score", "comment_count", "total_count",
              "discussion_count", "issue_open", "issue_closed", "pr_open", "pr_closed",
              "visible", "top3_1", "top3_2", "top3_3", "error", "crawled_at"]
    with open(DST, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 统计
    ok_rows = [r for r in rows if r["status"] == "ok"]
    with_comments = [r for r in ok_rows if (r["comment_count"] or 0) > 0]
    scored = [r["avg_score"] for r in ok_rows if r["avg_score"]]
    print(f"原始记录 {n_total}（错误 {n_err}）→ 去重后 {len(rows)} 个模型")
    print(f"成功解析 {len(ok_rows)}；有评论的模型 {len(with_comments)}")
    if scored:
        print(f"平均评分均值 {sum(scored)/len(scored):.2f}，有评分模型 {len(scored)}")
    from collections import Counter
    kw = Counter()
    for r in ok_rows:
        for k in (r["top3_1"], r["top3_2"], r["top3_3"]):
            if k:
                kw[k] += 1
    print("Top3 关键词频次前 15:", kw.most_common(15))
    print("输出:", DST)


if __name__ == "__main__":
    main()
