"""
Upgrade module for controlled LLM and plugin evolution.

This package groups the core contracts used to plan candidate upgrades without
mixing LLM optimization and plugin evolution into a single file.

Includes automated upgrade skills inspired by Superpowers framework:
- AtomicUpgradePlanner: Automated task decomposition
- AutomatedRootCauseAnalyzer: Systematic failure analysis
- AutomatedTwoStageReviewer: Automated code quality review
"""

from zentex.upgrade.models import (
    LLMUpgradeDecision,
    LLMUpgradeIntentRequest,
    PluginEvolutionDecision,
    PluginEvolutionIntentRequest,
    UpgradeDecisionAction,
)
from zentex.upgrade.execution import UpgradeExecutionService
from zentex.upgrade.service import UpgradeFacade
from zentex.upgrade.versioning import UpgradeChangeScope, derive_candidate_version

# Automated upgrade skills (Superpowers-inspired)
from zentex.upgrade.skills import (
    AtomicUpgradePlanner,
    AtomicTask,
    AtomicUpgradePlan,
    AutomatedRootCauseAnalyzer,
    RootCauseAnalysis,
    AutomatedTwoStageReviewer,
    ReviewResult,
)

__all__ = [
    # Core models
    "LLMUpgradeDecision",
    "LLMUpgradeIntentRequest",
    "PluginEvolutionDecision",
    "PluginEvolutionIntentRequest",
    "UpgradeChangeScope",
    "UpgradeDecisionAction",
    
    # Services
    "UpgradeExecutionService",
    "UpgradeFacade",
    "derive_candidate_version",
    
    # Automated upgrade skills (Superpowers-inspired)
    "AtomicUpgradePlanner",
    "AtomicTask",
    "AtomicUpgradePlan",
    "AutomatedRootCauseAnalyzer",
    "RootCauseAnalysis",
    "AutomatedTwoStageReviewer",
    "ReviewResult",
]
