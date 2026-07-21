# -*- coding: utf-8 -*-
"""魔搭评论正文爬虫 - API 直采版。

在 comments/summary 汇总数据基础上，抓取有社区互动的模型的完整内容：
- 4 类主帖：comment（评价）、issue（open/closed）、discussion、pr（open/closed）
- 每个主帖的全部回复（/comments/{cid} 接口）
- 富文本 Content 已提取为纯文本 content_text

模型清单来源: ms_comments_all.jsonl 中 summary 各计数 > 0 的模型。
输出: modelscope_output/ms_comment_texts.jsonl（每行一个模型）
状态: modelscope_output/state_ms_comment_texts.json（断点续爬）

环境变量 MS_TEXT_LIMIT=N 可限制本次处理的模型数（本地调试用）。
"""
import json
import os
import sys
import time
import threading
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).resolve().parent
SUMMARY_FILE = BASE_DIR / "modelscope_output" / "ms_comments_all.jsonl"
OUTPUT_FILE = BASE_DIR / "modelscope_output" / "ms_comment_texts.jsonl"
STATE_FILE = BASE_DIR / "modelscope_output" / "state_ms_comment_texts.json"

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"}
API = "https://www.modelscope.cn/api/v1"

# (Type, OpenStatus) 组合；OpenStatus 为 None 表示不带该参数。
# 具体类型在前（主帖可获得 open/closed 标签），Type=comment 兜底放最后
# （它返回全部类型的合集，用于接住前面组合可能遗漏的主帖）。
COMBOS = [
    ("issue", "open"),
    ("issue", "closed"),
    ("pr", "open"),
    ("pr", "closed"),
    ("discussion", None),
    ("comment", None),
]

MAX_WORKERS = 5
PAGE_SIZE = 100
SAVE_EVERY = 50
ABORT_AFTER = 50
LIMIT = int(os.environ.get("MS_TEXT_LIMIT", "0") or 0)

abort_flag = threading.Event()


def extract_text(node):
    """从富文本树提取纯文本。结构为 [tag, attrs, ...children]，
    attrs 含 data-type=leaf 时后一个元素是字符串。"""
    parts = []
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        # leaf: [tag, {"data-type": "leaf"}, "文本"]
        if len(node) >= 3 and isinstance(node[1], dict) and node[1].get("data-type") == "leaf":
            if isinstance(node[2], str):
                return node[2]
        for child in node:
            t = extract_text(child)
            if t:
                parts.append(t)
    return "".join(parts)


def content_to_text(raw):
    if not raw:
        return ""
    try:
        tree = json.loads(raw)
        return extract_text(tree).strip()
    except Exception:
        return str(raw)[:500]


def get_json(url, retries=3):
    """带重试的 GET。返回 (json_dict, ok)。ok=False 表示网络类失败。"""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json(), True
            if r.status_code in (429, 403):
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                return {}, True  # 无此资源，视为确定答复
            if attempt < retries - 1:
                time.sleep(1 + attempt)
                continue
            return {}, False
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            return {}, False
    return {}, False


def fetch_threads(model_id, ctype, open_status):
    """翻页抓取某类主帖，返回 (threads, ok)。"""
    threads = []
    offset = 0
    while True:
        url = (f"{API}/models/{model_id}/comments/list"
               f"?Offset={offset}&PageSize={PAGE_SIZE}&PageNumber={offset // PAGE_SIZE + 1}&Type={ctype}")
        if open_status:
            url += f"&OpenStatus={open_status}"
        j, ok = get_json(url)
        if not ok:
            return threads, False
        data = j.get("Data") or {}
        batch = data.get("Comments") or []
        threads.extend(batch)
        total = data.get("TotalCount") or 0
        if len(batch) < PAGE_SIZE or len(threads) >= total:
            break
        offset += PAGE_SIZE
        time.sleep(0.15)
    return threads, True


def fetch_replies(model_id, comment_id):
    """抓取一个主帖的全部回复。"""
    url = f"{API}/models/{model_id}/comments/{comment_id}?PageSize=1000&Offset=0"
    j, ok = get_json(url)
    if not ok:
        return [], False
    return (j.get("Data") or {}).get("Comments") or [], True


def slim_creator(c):
    c = c or {}
    return {"id": c.get("Id"), "name": c.get("Name"), "nickname": c.get("NickName")}


def fetch_model(model_id):
    """抓取一个模型的全部主帖+回复。返回 (record, definitive)。"""
    record = {"model_id": model_id, "status": "success", "crawled_at": time.time()}
    all_threads = []
    seen_ids = set()  # Type=comment 返回全部类型主帖，与 issue/pr 组合重叠，按 id 去重
    net_fail = False

    for ctype, open_status in COMBOS:
        if abort_flag.is_set():
            break
        raw_threads, ok = fetch_threads(model_id, ctype, open_status)
        if not ok:
            net_fail = True
            continue
        for t in raw_threads:
            tid = t.get("Id")
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            replies = []
            if (t.get("TotalChildren") or 0) > 0:
                reps, rok = fetch_replies(model_id, t.get("Id"))
                if rok:
                    replies = [{
                        "id": r.get("Id"),
                        "content_text": content_to_text(r.get("Content")),
                        "creator": slim_creator(r.get("Creator")),
                        "gmt_created": r.get("GmtCreated"),
                        "favorite_count": r.get("FavoriteCount"),
                    } for r in reps]
                time.sleep(0.15)
            all_threads.append({
                "id": t.get("Id"),
                "type": t.get("Type") or ctype,
                "open_status": open_status,
                "is_open": t.get("IsOpen"),
                "title": t.get("Title") or "",
                "content_text": content_to_text(t.get("Content")),
                "score": t.get("Score"),
                "favorite_count": t.get("FavoriteCount"),
                "creator": slim_creator(t.get("Creator")),
                "gmt_created": t.get("GmtCreated"),
                "total_children": t.get("TotalChildren") or 0,
                "tags": t.get("Tags") or [],
                "replies": replies,
            })
        time.sleep(0.15)

    record["threads"] = all_threads
    record["thread_count"] = len(all_threads)
    record["reply_count"] = sum(len(t["replies"]) for t in all_threads)
    if net_fail and not all_threads:
        record["status"] = "error"
        record["error"] = "network failure on all combos"
        return record, False
    if net_fail:
        record["partial"] = True
    return record, True


def load_active_models():
    """从汇总数据筛选有社区互动的模型（去重）。"""
    active = {}
    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            mid = r.get("model_id")
            if not mid or mid in active:
                continue
            for it in r.get("api_intercepts") or []:
                d = (it.get("data") or {}).get("Data") or {}
                keys = ("Count", "DiscussionCount", "IssueOpenCount",
                        "IssueClosedCount", "PrOpenCount", "PrClosedCount", "TotalCount")
                if any((d.get(k) or 0) > 0 for k in keys):
                    active[mid] = True
                    break
    return sorted(active.keys())


def main():
    if not SUMMARY_FILE.exists():
        print(f"File not found: {SUMMARY_FILE}", flush=True)
        sys.exit(2)

    active = load_active_models()

    completed = set()
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            completed = set(json.load(f))

    todo = [m for m in active if m not in completed]
    if LIMIT > 0:
        todo = todo[:LIMIT]
    print(f"Active models: {len(active)}, Completed: {len(completed)}, Remaining: {len(todo)}", flush=True)

    consecutive_errors = 0
    done_this_run = 0

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_model = {executor.submit(fetch_model, m): m for m in todo}
            for future in as_completed(future_to_model):
                if abort_flag.is_set():
                    break
                m_id = future_to_model[future]
                try:
                    record, definitive = future.result()
                except Exception as e:
                    record = {"model_id": m_id, "status": "error",
                              "error": str(e), "crawled_at": time.time()}
                    definitive = False

                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_f.flush()

                if definitive:
                    completed.add(m_id)
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    if consecutive_errors >= ABORT_AFTER:
                        print("Too many consecutive errors, aborting.", flush=True)
                        abort_flag.set()
                        break

                done_this_run += 1
                if done_this_run % SAVE_EVERY == 0:
                    with open(STATE_FILE, "w", encoding="utf-8") as sf:
                        json.dump(list(completed), sf)
                    print(f"Progress: +{done_this_run}, total done {len(completed)}", flush=True)

    with open(STATE_FILE, "w", encoding="utf-8") as sf:
        json.dump(list(completed), sf)
    print(f"Finished. +{done_this_run} this run, total done {len(completed)}", flush=True)
    if abort_flag.is_set():
        sys.exit(3)


if __name__ == "__main__":
    main()
