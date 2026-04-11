"""
Plugin upgrade package.

This package contains the planning contracts and service entrypoint for
OpenHands-based plugin evolution jobs.
"""

from zentex.upgrade.plugin.models import (
    PluginCreationCandidate,
    PluginCreationExecutionPlan,
    PluginCreationRequest,
    PluginEvolutionAction,
    PluginUpgradeCandidate,
    PluginUpgradeExecutionPlan,
    PluginUpgradeRequest,
)
from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime
from zentex.upgrade.plugin.service import OpenHandsPluginUpgradeService

__all__ = [
    "OpenHandsPluginUpgradeService",
    "PluginCreationCandidate",
    "PluginCreationExecutionPlan",
    "PluginCreationRequest",
    "PluginEvolutionAction",
    "PluginEvolutionRuntime",
    "PluginUpgradeCandidate",
    "PluginUpgradeExecutionPlan",
    "PluginUpgradeRequest",
]
