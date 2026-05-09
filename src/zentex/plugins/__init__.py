from __future__ import annotations

"""
Zentex Plugin Governance & Management System.

This module provides the central management bus for all plugin families,
enforcing registration-based authority and logical isolation.
"""

from zentex.plugins.unified_plugin_bus import (
    PluginFamily,
    PluginInvocationPlan,
    PluginInvocationResult,
    PluginSelectionDecision,
    UnifiedPluginBus,
    UnifiedPluginRegistration,
    UnifiedPluginSpec,
)

__all__ = [
    "PluginFamily",
    "PluginInvocationPlan",
    "PluginInvocationResult",
    "PluginSelectionDecision",
    "UnifiedPluginBus",
    "UnifiedPluginRegistration",
    "UnifiedPluginSpec",
]
