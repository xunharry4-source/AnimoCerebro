from __future__ import annotations

from typing import Any

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.plugin_family import (
    AlternativeSpec,
    ObjectiveSpec,
    PostureSpec,
    RedlinePluginSpec,
)


class BaselineRedlineOracle(RedlinePluginSpec):
    plugin_id: str = "baseline_redline_oracle"
    version: str = "1.0.0"
    feature_code: str = "redline.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["redline_regression"]
    revocation_reasons: list[str] = []

    def get_forbidden_zones(self) -> list[dict[str, Any]]:
        return [
            {
                "zone": "state_fabrication",
                "severity": "critical",
                "forbidden_actions": [
                    "fake_runtime_state",
                    "hide_plugin_failure",
                    "skip_audit_logging",
                ],
            },
            {
                "zone": "unsafe_execution",
                "severity": "high",
                "forbidden_actions": [
                    "unconfirmed_destructive_write",
                    "silent_external_side_effect",
                ],
            },
        ]


class BaselineAlternativeOracle(AlternativeSpec):
    plugin_id: str = "baseline_alternative_oracle"
    version: str = "1.0.0"
    feature_code: str = "alternative.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["alternative_strategy_regression"]
    revocation_reasons: list[str] = []

    def get_downgrade_options(self, block_context: dict[str, Any]) -> list[Any]:
        blocked = block_context.get("blocked_reason") or block_context.get("reason") or "primary_path_blocked"
        return [
            {
                "strategy": "read_only_audit_mode",
                "trigger": blocked,
                "cost": "low",
            },
            {
                "strategy": "request_human_confirmation",
                "trigger": "write_or_permission_boundary_detected",
                "cost": "medium",
            },
            {
                "strategy": "collect_more_evidence_then_replan",
                "trigger": "insufficient_confidence",
                "cost": "medium",
            },
        ]


class BaselineObjectiveOracle(ObjectiveSpec):
    plugin_id: str = "baseline_objective_oracle"
    version: str = "1.0.0"
    feature_code: str = "objective.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["objective_queue_regression"]
    revocation_reasons: list[str] = []

    def refine_task_queue(self, task_queue: list[Any], context: dict[str, Any]) -> list[Any]:
        if not isinstance(task_queue, list):
            return []
        return list(task_queue)


class BaselinePostureOracle(PostureSpec):
    plugin_id: str = "baseline_posture_oracle"
    version: str = "1.0.0"
    feature_code: str = "posture.core"
    is_concurrency_safe: bool = True
    status: PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE
    health_status: PluginHealthStatus = PluginHealthStatus.HEALTHY
    rollback_conditions: list[str] = ["posture_regression"]
    revocation_reasons: list[str] = []

    def apply_posture(self, decision_trace: dict[str, Any]) -> dict[str, Any]:
        return {
            "evaluation_style": "evidence_first",
            "risk_tolerance": "low",
            "confirmation_strategy": "confirm_on_write",
            "action_rhythm": "bounded_incremental_steps",
        }


def build_default_redline_oracle() -> BaselineRedlineOracle:
    return BaselineRedlineOracle()


def build_default_alternative_oracle() -> BaselineAlternativeOracle:
    return BaselineAlternativeOracle()


def build_default_objective_oracle() -> BaselineObjectiveOracle:
    return BaselineObjectiveOracle()


def build_default_posture_oracle() -> BaselinePostureOracle:
    return BaselinePostureOracle()
