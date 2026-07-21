"""清洗制度文本：去掉导航栏/页脚，保留正文"""
import os, re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")

# 导航/页脚关键词（行首匹配）
NAV_PATTERNS = [
    '首页', '模型库', '数据集', '创空间', '文档', '社区',
    'Skills 中心', 'MCP 广场', 'AIGC 专区', '登录 / 注册',
    'Repo ?', 'Swift', 'ModelScope-Agent',
    '浙公网安备', '浙ICP备',
]
NAV_RE = re.compile(r'^(' + '|'.join(re.escape(p) for p in NAV_PATTERNS) + r')')

FILES = [
    ("governance_user_agreement.txt", "用户协议"),
    ("governance_privacy_policy.txt", "隐私政策"),
    ("governance_about.txt", "关于我们"),
    ("governance_content_review.txt", "内容合规审核"),
    ("governance_open_source_code_of_conduct.txt", "开源行为准则"),
    ("governance_ai_ethics.txt", "人工智能伦理倡议书"),
    ("governance_contact_us.txt", "联系我们"),
]

print("清洗制度文本\n")

for filename, label in FILES:
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  [跳过] {filename} 不存在")
        continue

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 分离 header 和正文
    sep = "=" * 80
    if sep in content:
        header, _, body = content.partition(sep)
    else:
        header = ""
        body = content

    # 清洗正文：去掉导航行
    lines = body.strip().split("\n")
    # 找到正文起始（第一个不含导航关键词的实质性行）
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if NAV_RE.match(stripped):
            continue
        # 找到标题行（通常与filename对应）
        start_idx = i
        break

    # 也去掉结尾的页脚
    end_idx = len(lines)
    # 从末尾往前找，去掉导航/页脚行
    for i in range(len(lines) - 1, start_idx, -1):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if NAV_RE.match(stripped):
            continue
        # 如果是页脚信息
        if '2022-2026' in stripped or 'ModelScope.cn' in stripped:
            continue
        end_idx = i + 1
        break

    cleaned_lines = lines[start_idx:end_idx]
    cleaned = "\n".join(cleaned_lines).strip()

    # 去掉空行过多的部分
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    # 重新写文件
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)  # 保留原始完整文件

    # 保存清洗版
    clean_path = os.path.join(OUTPUT_DIR, filename.replace(".txt", "_clean.txt"))
    with open(clean_path, "w", encoding="utf-8") as f:
        f.write(cleaned)

    # 统计
    original_size = len(body.strip())
    clean_size = len(cleaned)
    print(f"  {label}: {original_size} -> {clean_size} chars -> {os.path.basename(clean_path)}")
    # 预览
    for line in cleaned.split("\n")[:3]:
        if line.strip():
            print(f"    | {line[:70]}")
    print()

print("\n=== 原始文件尺寸 ===")
for filename, label in FILES:
    fpath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(fpath):
        size = os.path.getsize(fpath)
        print(f"  {filename:40s} {size:>8,} bytes")