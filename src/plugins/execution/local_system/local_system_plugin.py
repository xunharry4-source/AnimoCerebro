from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.contracts import ActionIntent, ActionStatus
from zentex.plugins.models import PluginLifecycleStatus


class LocalSystemExecutor(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "execution_local_system"
    version: str = "1.0.0"
    feature_code: str = "execution.system"
    display_name: str = "Local System Executor"
    description: str = "Produce a deterministic local-system execution receipt."
    behavior_key: str = "execution_local_system"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    execution_domain: str = "system"
    requires_cloud_audit: bool = False
    rollback_conditions: list[str] = Field(default_factory=lambda: ["execution_regression"])
    revocation_reasons: list[str] = Field(default_factory=lambda: ["reserved_for_runtime_audit"])

    def execute_action(self, intent: ActionIntent | dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if isinstance(intent, dict):
            normalized_intent = ActionIntent.model_validate(intent)
        else:
            normalized_intent = intent
        evidence_input = json.dumps(
            {
                "action_type": normalized_intent.action_type,
                "target": normalized_intent.target,
                "parameters": normalized_intent.parameters,
                "workspace": context.get("workspace"),
            },
            sort_keys=True,
        )
        return {
            "status": ActionStatus.succeeded.value,
            "execution_domain": self.execution_domain,
            "action_hash": hashlib.sha256(evidence_input.encode("utf-8")).hexdigest(),
            "workspace": context.get("workspace"),
        }


def build_default_local_system_executor() -> LocalSystemExecutor:
    return LocalSystemExecutor()
