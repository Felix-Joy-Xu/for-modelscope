"""
__init__.py — 采集器包
"""
from collectors.m1_pr_lifecycle import collect_m1_for_repo
from collectors.m2_contributor_mobility import collect_m2_contributors, collect_m2_mobility
from collectors.m4_accountability import collect_m4_for_repo
