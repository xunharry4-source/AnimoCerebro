from __future__ import annotations

from typing import Any, Dict, List
from zentex.core.plugin_base import PluginLifecycleStatus, PluginHealthStatus
from zentex.core.plugin_family import IdentityPackageSpec


class RolePackPlugin(IdentityPackageSpec):
    """
    G10 Identity Package Plugin for Role definitions.
    """
    
    plugin_id: str = "identity_role_pack_base"
    pack_type: str = "role_pack"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["logic_drift"]
    revocation_reasons: List[str] = []

    def get_payload(self) -> Dict[str, Any]:
        return {
            "identity_role": "Zentex Cognitive Brain",
            "active_role_default": "System Analyst",
            "task_role_mapping": {
                "coding": "Autonomous Developer",
                "audit": "Compliance Officer"
            }
        }


class ConstraintPackPlugin(IdentityPackageSpec):
    """
    G10 Identity Package Plugin for Constraints (Non-bypassable Redlines).
    """
    
    plugin_id: str = "identity_constraint_pack_base"
    pack_type: str = "constraint_pack"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: List[str] = ["logic_drift"]
    revocation_reasons: List[str] = []

    def get_payload(self) -> Dict[str, Any]:
        return {
            "non_bypassable_constraints": [
                "No PII leakage",
                "Strict audit trail reporting",
                "Verify all physical execution effects"
            ]
        }
