from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_ids import NINE_QUESTION_Q7
from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals


class WhatElseCanIDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q7
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q7"
    display_name: str = "Q7: What else can I do?"
    description: str = "Generate fallback strategies and substitute actions."
    behavior_key: str = "q7_alternative_strategy"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    rollback_conditions: list[str] = Field(default_factory=lambda: ["unhandled_q7_failure"])
    revocation_reasons: list[str] = Field(default_factory=list)

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        plugin_service = context.get("plugin_service")
        functional_alternatives: list[dict[str, Any]] = []
        if plugin_service is not None:
            functional_alternatives = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={"block_context": dict(context)},
                trace_id=str(context.get("trace_id") or "q7"),
                originator_id=str(context.get("session_id") or "unknown-session"),
                caller_plugin_id=self.plugin_id,
            )
        proposals = [
            item.get("result")
            for item in functional_alternatives
            if item.get("status") == "done"
        ]
        return {
            "answer": "Primary path blocked; use fallback plans and bounded collaboration.",
            "confidence": 0.7,
            "alternative_strategy_profile": {
                "fallback_plans": ["switch to read-only audit mode"],
                "degradation_strategies": ["reduce scope to evidence collection only"],
                "collaboration_switches": ["request human review for blocked write path"],
                "exploratory_actions": ["inspect latest transcript for failure cause"],
                "functional_inputs": proposals,
            },
        }

    def run_tool(self, context: dict[str, Any]) -> dict[str, Any]:
        return self.execute(context)


def build_q7_what_else_can_i_do_plugin() -> WhatElseCanIDoPlugin:
    return WhatElseCanIDoPlugin()
