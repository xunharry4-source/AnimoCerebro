from __future__ import annotations

from typing import Any, Dict, Optional

from zentex.core.models import CognitiveToolSpec
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.safety.conflict_engine import CognitiveConflictReport


class BudgetConflictPlugin(CognitiveToolSpec):
    def detect_conflict(self, *, context: Dict[str, Any]) -> Optional[CognitiveConflictReport]:
        requested_tokens = int(context.get("requested_tokens", 0))
        token_budget = int(context.get("token_budget", 0))
        if requested_tokens <= token_budget:
            return None
        return CognitiveConflictReport(
            conflict_type="budget_conflict",
            severity="critical" if requested_tokens > token_budget * 2 else "high",
            suggested_resolution="reduce_reasoning_branch_count_or_pause_expansion",
            source_plugin_id=self.plugin_id,
            details={
                "requested_tokens": requested_tokens,
                "token_budget": token_budget,
            },
        )


def build_budget_conflict_plugin(
    *,
    plugin_id: str = "budget-conflict",
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> BudgetConflictPlugin:
    return BudgetConflictPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["budget_conflict_false_positive_spike"],
        revocation_reasons=["reserved_for_runtime_audit"],
        tool_type="budget_conflict_detector",
        purpose="Detect conflicts between requested reasoning scope and token budget.",
        input_schema={"type": "object", "required": ["requested_tokens", "token_budget"]},
        output_schema={"type": "object", "required": ["requested_tokens", "token_budget"]},
        required_context=["requested_tokens", "token_budget"],
        trigger_conditions=["always"],
        behavior_key="cognitive_conflict_detection",
        supports_multiple_plugins=True,
        is_default_version=True,
        is_official_release=True,
        do_not_use_when=["execution_requested"],
    )
