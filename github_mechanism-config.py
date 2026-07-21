"""
GitHub 机制化数据采集 — 配置文件
对应论文 M1–M4 数据—机制对应表
"""

import os
from datetime import datetime

# ============================================================
# GitHub API 配置
# ============================================================
# 设置你的 GitHub Personal Access Token（建议 fine-grained token）
# 可通过环境变量 GITHUB_TOKEN 设置，或直接填写
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# API 基础设置
API_BASE = "https://api.github.com"
REQUESTS_PER_SECOND = 1.0          # 请求限速（每秒请求数）
MAX_RETRIES = 3                    # 失败重试次数
PER_PAGE = 100                     # 每页结果数（GitHub 最大 100）

# ============================================================
# 数据存储
# ============================================================
DB_PATH = os.path.join(os.path.dirname(__file__), "mechanism_data.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ============================================================
# 目标仓库配置
# ============================================================
# 选择已明确引入 AI 编程工具的大型开源仓库
# 格式: {"owner/repo": "AI工具引入时间点（用于前后对比）"}
#
# 建议选择标准:
#   1. 有公开讨论 AI 工具使用的记录（PR/Issue 中提及 Copilot 等）
#   2. PR/Issue 活跃度高，历史记录丰富
#   3. 有 bot 标签、自动化检查等基础设施
#   4. 覆盖不同组织类型（大厂/中型/社区驱动）
#
# ⚠️ 请根据你的研究需要替换为实际目标仓库
TARGET_REPOS = {
    "microsoft/vscode":         {"ai_adoption_date": "2023-06-01", "org_type": "大厂平台"},
    "facebook/react":           {"ai_adoption_date": "2023-06-01", "org_type": "大厂平台"},
    "vercel/next.js":           {"ai_adoption_date": "2023-06-01", "org_type": "中型互联网"},
    "langchain-ai/langchain":   {"ai_adoption_date": "2023-03-01", "org_type": "AI原生"},
    "openai/openai-python":     {"ai_adoption_date": "2023-01-01", "org_type": "AI原生"},
}

# 数据采集时间窗口（前后各12个月对比）
LOOKBACK_MONTHS = 12
LOOKAHEAD_MONTHS = 12

# 每个仓库最多采集的 PR/Issue 数量（避免超量）
MAX_PRS_PER_REPO = 2000
MAX_ISSUES_PER_REPO = 2000

# ============================================================
# M1: 注意力迁移 — 审查负担指标
# ============================================================
# AI 生成代码相关标签（用于识别 AI 参与的 PR）
M1_AI_LABELS = [
    "copilot", "ai-generated", "ai-assisted", "bot",
    "auto-generated", "automated", "github-actions",
]

# AI 相关关键词（在 PR 标题/描述中搜索）
M1_AI_KEYWORDS = [
    "copilot", "ai-generated", "ai generated", "chatgpt",
    "gpt-4", "gpt4", "claude", "ai assisted", "ai-assisted",
    "llm", "code generation", "auto-generated",
    "github copilot", "codewhisperer", "cursor",
    "tabnine", "ai coding", "ai suggestion",
]

# ============================================================
# M3: 过程可见性 — 管理与 bot 介入
# ============================================================
# 已知的自动化 bot 账户名模式
M3_BOT_PATTERNS = [
    "bot", "automation", "ci-bot", "codecov", "dependabot",
    "renovate", "github-actions", "mergify", "stale",
    "vercel", "netlify", "sonarcloud", "snyk",
]

# 管理/合规相关关键词
M3_VISIBILITY_KEYWORDS = [
    "compliance", "policy", "required check", "mandatory review",
    "code owner", "CODEOWNERS", "approval required",
    "security review", "audit", "sign-off",
    "must be reviewed", "needs approval",
]

# ============================================================
# M4: 问责—权力鸿沟 — 话语编码
# ============================================================
# 责任归因话语关键词
M4_ACCOUNTABILITY_KEYWORDS = {
    # 个体化归因（指向具体人的责任追溯）
    "individual_blame": [
        "who broke", "who introduced", "your fault",
        "you broke", "caused by", "responsible for",
        "introduced by", "blame", "whose code",
        "revert", "should have caught", "missed in review",
        "why wasn't this caught", "who approved",
    ],
    # AI 归因（将问题归因于 AI 工具）
    "ai_attribution": [
        "copilot generated", "ai generated", "ai-generated",
        "auto-generated bug", "generated code", "ai suggestion",
        "copilot bug", "llm hallucination", "hallucinated",
        "ai introduced", "machine generated",
    ],
    # 系统/流程归因（将问题归因于制度缺陷）
    "systemic_attribution": [
        "process failure", "review process", "ci should have",
        "test coverage", "linting", "pipeline",
        "our process", "workflow issue", "systemic",
        "we need better", "tooling gap",
    ],
    # 问责鸿沟话语（背书但无法控制质量）
    "accountability_gap": [
        "approved but didn't understand",
        "rubber stamp", "rubber-stamp",
        "can't verify", "too complex to review",
        "no time to review properly",
        "signed off without understanding",
        "lgtm without reading",  # Looks Good To Me 但没细看
        "trust but verify",
        "black box", "can't trace",
    ],
}

# Bug 相关标签（用于筛选事故/缺陷 issue）
M4_BUG_LABELS = [
    "bug", "defect", "regression", "incident",
    "production-issue", "hotfix", "critical",
    "severity", "crash", "broken",
]

# ============================================================
# M2: 技能权重重置 — 贡献者流动性
# ============================================================
# 分析 top N 贡献者的跨仓库活动
M2_TOP_CONTRIBUTORS = 50
# 外部活动采集的时间范围（月）
M2_EXTERNAL_LOOKBACK_MONTHS = 24
