from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from zentex.common.plugin_ids import COGNITIVE_BUDGET_CONFLICT
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals
from zentex.safety.conflict_engine import CognitiveConflictReport


class BudgetConflictPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = COGNITIVE_BUDGET_CONFLICT
    version: str = "1.0.0"
    feature_code: str = "cognitive.budget_conflict"
    display_name: str = "Budget Conflict"
    description: str = "Detect conflicts between requested reasoning scope and budget."
    behavior_key: str = "cognitive_conflict_detection"
    lifecycle_status: str = "active"
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def detect_conflict(self, *, context: dict[str, Any]) -> Optional[CognitiveConflictReport]:
        plugin_service = context.get("plugin_service")
        functional_inputs: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_inputs = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters=dict(context),
                trace_id=str(context.get("trace_id") or "budget-conflict"),
                originator_id=str(context.get("session_id") or "budget-conflict"),
                caller_plugin_id=self.plugin_id,
            )
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
                "functional_inputs": functional_inputs,
            },
        )


def build_budget_conflict_plugin() -> BudgetConflictPlugin:
    return BudgetConflictPlugin()
