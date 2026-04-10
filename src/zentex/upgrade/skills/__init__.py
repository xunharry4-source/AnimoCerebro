"""
Upgrade Skills Module - Automated upgrade enhancement skills.

This module integrates automated skills inspired by Superpowers framework
to enhance the upgrade process without requiring human interaction.

Skills included:
- AtomicPlanner: Automatically decomposes upgrade proposals into atomic tasks
- AutoDebugger: Performs automated root cause analysis on failures
- AutoReviewer: Conducts two-stage automated code review
"""

from zentex.upgrade.skills.atomic_planner import AtomicUpgradePlanner, AtomicTask, AtomicUpgradePlan
from zentex.upgrade.skills.auto_debugger import AutomatedRootCauseAnalyzer, RootCauseAnalysis
from zentex.upgrade.skills.auto_reviewer import AutomatedTwoStageReviewer, ReviewResult

__all__ = [
    "AtomicUpgradePlanner",
    "AtomicTask", 
    "AtomicUpgradePlan",
    "AutomatedRootCauseAnalyzer",
    "RootCauseAnalysis",
    "AutomatedTwoStageReviewer",
    "ReviewResult",
]
