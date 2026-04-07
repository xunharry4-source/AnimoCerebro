"""
Upgrade module for controlled LLM and plugin evolution.

This package groups the core contracts used to plan candidate upgrades without
mixing LLM optimization and plugin evolution into a single file.
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

__all__ = [
    "LLMUpgradeDecision",
    "LLMUpgradeIntentRequest",
    "PluginEvolutionDecision",
    "PluginEvolutionIntentRequest",
    "UpgradeChangeScope",
    "UpgradeDecisionAction",
    "UpgradeExecutionService",
    "UpgradeFacade",
    "derive_candidate_version",
]
