"""
机制化分析模块
按 M1–M4 + H1–H3 对应表生成分析报告

分析维度（对应论文数据—机制对应表）：
  M1: PR 合并周期前后对比、review 密度与 AI 标记的相关性
  M2: 贡献者外部活动的前后变化
  M3: bot/自动化介入的增长趋势
  M4: 问责话语的类别分布与时间趋势
"""

import os
import json
import logging
from datetime import datetime
from collections import defaultdict
from typing import Dict, List

from database import MechanismDB
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def analyze_m1(db: MechanismDB) -> dict:
    """
    M1 分析：审查负担的前后对比

    核心问题（对应 H1）：
    AI 工具引入后，PR 审查周期是否延长？
    有 AI 标记的 PR 是否 review 密度更高？
    """
    results = {}

    # 1. 前后对比：合并周期
    for period in ["pre_ai", "post_ai"]:
        rows = db.query("""
            SELECT
                repo_id,
                COUNT(*) as pr_count,
                AVG(cycle_hours) as avg_cycle_hours,
                AVG(review_comments) as avg_review_comments,
                AVG(review_rounds) as avg_review_rounds,
                AVG(changes_requested) as avg_changes_requested,
                AVG(unique_reviewers) as avg_unique_reviewers,
                AVG(commits_count) as avg_commits,
                AVG(additions + deletions) as avg_code_churn
            FROM m1_pr_lifecycle
            WHERE period = ? AND state = 'merged' AND cycle_hours IS NOT NULL
            GROUP BY repo_id
        """, (period,))
        results[f"merged_prs_{period}"] = [dict(r) for r in rows]

    # 2. AI 标记 vs 非 AI 标记 PR 的审查负担对比
    rows = db.query("""
        SELECT
            repo_id,
            CASE WHEN has_ai_label OR has_ai_keyword THEN 'ai_flagged' ELSE 'no_ai_flag' END as ai_status,
            COUNT(*) as pr_count,
            AVG(cycle_hours) as avg_cycle_hours,
            AVG(review_comments) as avg_review_comments,
            AVG(review_rounds) as avg_review_rounds,
            AVG(changes_requested) as avg_changes_requested
        FROM m1_pr_lifecycle
        WHERE state = 'merged' AND cycle_hours IS NOT NULL
        GROUP BY repo_id, ai_status
    """)
    results["ai_flag_comparison"] = [dict(r) for r in rows]

    # 3. 按月趋势
    rows = db.query("""
        SELECT
            repo_id,
            strftime('%Y-%m', created_at) as month,
            period,
            COUNT(*) as pr_count,
            AVG(cycle_hours) as avg_cycle_hours,
            AVG(review_comments) as avg_review_comments,
            SUM(has_ai_label OR has_ai_keyword) as ai_flagged_count
        FROM m1_pr_lifecycle
        WHERE state = 'merged'
        GROUP BY repo_id, month, period
        ORDER BY repo_id, month
    """)
    results["monthly_trend"] = [dict(r) for r in rows]

    return results


def analyze_m2(db: MechanismDB) -> dict:
    """
    M2 分析：贡献者流动性的前后变化

    核心问题（对应 H2）：
    AI 工具深度集成仓库的 top 贡献者，其外部活动是否下降？
    """
    results = {}

    # 前后对比
    rows = db.query("""
        SELECT
            home_repo_id,
            observation_period,
            COUNT(*) as contributor_count,
            AVG(external_repos_count) as avg_external_repos,
            AVG(external_prs_count) as avg_external_prs,
            AVG(external_issues_count) as avg_external_issues,
            AVG(external_commits_count) as avg_external_commits,
            SUM(CASE WHEN external_repos_count = 0 THEN 1 ELSE 0 END) as inactive_externally
        FROM m2_contributor_mobility
        WHERE observation_period IN ('pre_ai', 'post_ai')
        GROUP BY home_repo_id, observation_period
    """)
    results["mobility_comparison"] = [dict(r) for r in rows]

    # 个体级别变化（前-后配对）
    rows = db.query("""
        SELECT
            pre.username,
            pre.home_repo_id,
            pre.external_repos_count as pre_external_repos,
            post.external_repos_count as post_external_repos,
            pre.external_prs_count as pre_external_prs,
            post.external_prs_count as post_external_prs,
            (post.external_repos_count - pre.external_repos_count) as repos_change,
            (post.external_prs_count - pre.external_prs_count) as prs_change
        FROM m2_contributor_mobility pre
        JOIN m2_contributor_mobility post
            ON pre.username = post.username
            AND pre.home_repo_id = post.home_repo_id
        WHERE pre.observation_period = 'pre_ai'
            AND post.observation_period = 'post_ai'
        ORDER BY repos_change ASC
    """)
    results["individual_changes"] = [dict(r) for r in rows]

    return results


def analyze_m3(db: MechanismDB) -> dict:
    """
    M3 分析：过程可见性与自动化控制趋势

    核心问题：
    bot/自动化介入是否在 AI 引入后增加？
    合规关键词出现频率是否上升？
    """
    results = {}

    # 前后对比
    for period in ["pre_ai", "post_ai"]:
        rows = db.query("""
            SELECT
                repo_id,
                COUNT(*) as pr_count,
                AVG(bot_comments) as avg_bot_comments,
                AVG(bot_reviews) as avg_bot_reviews,
                AVG(automated_checks) as avg_automated_checks,
                AVG(visibility_keywords_count) as avg_visibility_keywords,
                SUM(CASE WHEN visibility_keywords_count > 0 THEN 1 ELSE 0 END) as prs_with_visibility_kw
            FROM m3_pr_visibility
            WHERE period = ?
            GROUP BY repo_id
        """, (period,))
        results[f"visibility_{period}"] = [dict(r) for r in rows]

    return results


def analyze_m4(db: MechanismDB) -> dict:
    """
    M4 分析：问责话语的类别分布

    核心问题（对应 H1 行为印证 + 论文 M4）：
    bug 类 issue 中的归因话语模式如何？
    AI 归因话语是否在 post_ai 时期增加？
    个体化归因 vs 系统性归因的比例如何变化？
    """
    results = {}

    # 前后对比：话语类别分布
    for period in ["pre_ai", "post_ai"]:
        rows = db.query("""
            SELECT
                repo_id,
                COUNT(*) as issue_count,
                SUM(is_bug) as bug_count,
                SUM(individual_blame_count) as total_individual_blame,
                SUM(ai_attribution_count) as total_ai_attribution,
                SUM(systemic_attribution_count) as total_systemic,
                SUM(accountability_gap_count) as total_gap,
                AVG(comments_count) as avg_comments,
                AVG(unique_commenters) as avg_commenters
            FROM m4_issue_discourse
            WHERE period = ?
            GROUP BY repo_id
        """, (period,))
        results[f"discourse_{period}"] = [dict(r) for r in rows]

    # Top 话语片段（用于定性引证）
    rows = db.query("""
        SELECT
            repo_id, issue_number, discourse_type,
            matched_keyword, context_text, author, created_at
        FROM m4_discourse_snippets
        WHERE discourse_type IN ('ai_attribution', 'accountability_gap')
        ORDER BY created_at DESC
        LIMIT 50
    """)
    results["top_snippets"] = [dict(r) for r in rows]

    # 话语类型频率统计
    rows = db.query("""
        SELECT
            discourse_type,
            COUNT(*) as count,
            COUNT(DISTINCT repo_id || '/' || issue_number) as unique_issues
        FROM m4_discourse_snippets
        GROUP BY discourse_type
        ORDER BY count DESC
    """)
    results["discourse_type_distribution"] = [dict(r) for r in rows]

    return results


def generate_report(db: MechanismDB) -> str:
    """生成完整的机制化分析报告。"""

    ensure_output_dir()

    m1 = analyze_m1(db)
    m2 = analyze_m2(db)
    m3 = analyze_m3(db)
    m4 = analyze_m4(db)

    # 生成 Markdown 报告
    report_lines = [
        "# GitHub 机制化数据分析报告",
        f"\n> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n---\n",
    ]

    # ==== M1 ====
    report_lines.append("## M1: 注意力迁移 — PR 审查负担分析\n")
    report_lines.append("### 前后对比（已合并 PR）\n")
    report_lines.append("| 仓库 | 时期 | PR数 | 平均合并周期(h) | 平均review评论 | 平均review轮次 | 平均退回次数 |")
    report_lines.append("|------|------|------|----------------|---------------|---------------|-------------|")

    for period_key in ["merged_prs_pre_ai", "merged_prs_post_ai"]:
        period_label = "AI前" if "pre" in period_key else "AI后"
        for row in m1.get(period_key, []):
            report_lines.append(
                f"| {row['repo_id']} | {period_label} | {row['pr_count']} | "
                f"{row['avg_cycle_hours']:.1f} | {row['avg_review_comments']:.1f} | "
                f"{row['avg_review_rounds']:.1f} | {row['avg_changes_requested']:.1f} |"
            )

    report_lines.append("\n### AI 标记 vs 非 AI 标记 PR 对比\n")
    report_lines.append("| 仓库 | AI状态 | PR数 | 平均合并周期(h) | 平均review评论 |")
    report_lines.append("|------|--------|------|----------------|---------------|")
    for row in m1.get("ai_flag_comparison", []):
        report_lines.append(
            f"| {row['repo_id']} | {row['ai_status']} | {row['pr_count']} | "
            f"{row['avg_cycle_hours']:.1f} | {row['avg_review_comments']:.1f} |"
        )

    # ==== M2 ====
    report_lines.append("\n---\n")
    report_lines.append("## M2: 技能权重重置 — 贡献者流动性分析\n")
    report_lines.append("### 前后对比\n")
    report_lines.append("| 仓库 | 时期 | 贡献者数 | 平均外部仓库数 | 平均外部PR数 | 外部不活跃人数 |")
    report_lines.append("|------|------|---------|--------------|-------------|--------------|")
    for row in m2.get("mobility_comparison", []):
        period_label = "AI前" if row["observation_period"] == "pre_ai" else "AI后"
        report_lines.append(
            f"| {row['home_repo_id']} | {period_label} | {row['contributor_count']} | "
            f"{row['avg_external_repos']:.1f} | {row['avg_external_prs']:.1f} | "
            f"{row['inactive_externally']} |"
        )

    # 个体级别变化
    changes = m2.get("individual_changes", [])
    if changes:
        declined = [c for c in changes if c["repos_change"] < 0]
        increased = [c for c in changes if c["repos_change"] > 0]
        unchanged = [c for c in changes if c["repos_change"] == 0]
        report_lines.append(
            f"\n**个体级别变化**: 外部活动减少 {len(declined)} 人, "
            f"增加 {len(increased)} 人, 不变 {len(unchanged)} 人"
        )

    # ==== M3 ====
    report_lines.append("\n---\n")
    report_lines.append("## M3: 过程可见性 — 自动化控制趋势\n")
    report_lines.append("| 仓库 | 时期 | PR数 | 平均bot评论 | 平均自动化检查 | 含合规关键词PR数 |")
    report_lines.append("|------|------|------|-----------|-------------|---------------|")
    for period_key in ["visibility_pre_ai", "visibility_post_ai"]:
        period_label = "AI前" if "pre" in period_key else "AI后"
        for row in m3.get(period_key, []):
            report_lines.append(
                f"| {row['repo_id']} | {period_label} | {row['pr_count']} | "
                f"{row['avg_bot_comments']:.2f} | {row['avg_automated_checks']:.2f} | "
                f"{row['prs_with_visibility_kw']} |"
            )

    # ==== M4 ====
    report_lines.append("\n---\n")
    report_lines.append("## M4: 问责—权力鸿沟 — 话语编码分析\n")
    report_lines.append("### 前后对比\n")
    report_lines.append("| 仓库 | 时期 | Issue数 | Bug数 | 个体归因 | AI归因 | 系统归因 | 问责鸿沟 |")
    report_lines.append("|------|------|--------|-------|---------|--------|---------|---------|")
    for period_key in ["discourse_pre_ai", "discourse_post_ai"]:
        period_label = "AI前" if "pre" in period_key else "AI后"
        for row in m4.get(period_key, []):
            report_lines.append(
                f"| {row['repo_id']} | {period_label} | {row['issue_count']} | "
                f"{row['bug_count']} | {row['total_individual_blame']} | "
                f"{row['total_ai_attribution']} | {row['total_systemic']} | "
                f"{row['total_gap']} |"
            )

    # 话语类型分布
    report_lines.append("\n### 话语类型总体分布\n")
    report_lines.append("| 话语类型 | 出现次数 | 涉及Issue数 |")
    report_lines.append("|---------|---------|-----------|")
    for row in m4.get("discourse_type_distribution", []):
        type_labels = {
            "individual_blame": "个体化归因",
            "ai_attribution": "AI归因",
            "systemic_attribution": "系统/流程归因",
            "accountability_gap": "问责鸿沟",
        }
        label = type_labels.get(row["discourse_type"], row["discourse_type"])
        report_lines.append(f"| {label} | {row['count']} | {row['unique_issues']} |")

    # 典型话语片段
    snippets = m4.get("top_snippets", [])
    if snippets:
        report_lines.append("\n### 典型话语片段（AI归因 & 问责鸿沟）\n")
        for s in snippets[:20]:
            type_labels = {
                "ai_attribution": "🤖 AI归因",
                "accountability_gap": "⚠️ 问责鸿沟",
            }
            label = type_labels.get(s["discourse_type"], s["discourse_type"])
            report_lines.append(
                f"**{label}** [{s['repo_id']}#{s['issue_number']}] "
                f"@{s['author']} ({s['created_at'][:10]})\n"
                f"> 关键词: `{s['matched_keyword']}`\n"
                f"> {s['context_text']}\n"
            )

    report_lines.append("\n---\n")
    report_lines.append("*本报告由 github_mechanism 分析工具自动生成*")

    report_text = "\n".join(report_lines)

    # 保存报告
    report_path = os.path.join(OUTPUT_DIR, "mechanism_analysis_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    # 保存原始数据为 JSON
    raw_path = os.path.join(OUTPUT_DIR, "mechanism_analysis_raw.json")
    raw_data = {
        "generated_at": datetime.now().isoformat(),
        "M1_attention_migration": m1,
        "M2_skill_mobility": m2,
        "M3_process_visibility": m3,
        "M4_accountability_discourse": m4,
    }
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"报告已保存: {report_path}")
    logger.info(f"原始数据已保存: {raw_path}")

    return report_text
