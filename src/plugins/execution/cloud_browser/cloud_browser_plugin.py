from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.contracts import ActionIntent, ActionStatus
from zentex.plugins.models import PluginLifecycleStatus


class CloudBrowserExecutor(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "execution_cloud_browser"
    version: str = "1.0.0"
    feature_code: str = "execution.browser"
    display_name: str = "Cloud Browser Executor"
    description: str = "Produce a deterministic browser/cloud execution receipt."
    behavior_key: str = "execution_cloud_browser"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    execution_domain: str = "browser"
    requires_cloud_audit: bool = True
    rollback_conditions: list[str] = Field(default_factory=lambda: ["execution_regression"])
    revocation_reasons: list[str] = Field(default_factory=lambda: ["reserved_for_runtime_audit"])

    def execute_action(self, intent: ActionIntent | dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if isinstance(intent, dict):
            normalized_intent = ActionIntent.model_validate(intent)
        else:
            normalized_intent = intent
        token = context.get("cloud_audit_token")
        evidence_input = json.dumps(
            {
                "action_type": normalized_intent.action_type,
                "target": normalized_intent.target,
                "parameters": normalized_intent.parameters,
                "audit_token": token,
            },
            sort_keys=True,
        )
        return {
            "status": ActionStatus.succeeded.value,
            "execution_domain": self.execution_domain,
            "cloud_audit_token": token,
            "cloud_response_hash": hashlib.sha256(evidence_input.encode("utf-8")).hexdigest(),
        }


def build_default_cloud_browser_executor() -> CloudBrowserExecutor:
    return CloudBrowserExecutor()
