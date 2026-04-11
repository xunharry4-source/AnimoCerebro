from __future__ import annotations

import hashlib
import json
from typing import Dict

from zentex.core.execution_spec import (
    ActionExecutionReceipt,
    ActionIntent,
    ActionStatus,
    ExecutionDomainPlugin,
)
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus


class CloudBrowserExecutor(ExecutionDomainPlugin):
    execution_domain: str = "browser"
    requires_cloud_audit: bool = True

    def execute_action(
        self,
        intent: ActionIntent,
        context: Dict[str, object],
    ) -> ActionExecutionReceipt:
        token = context.get("cloud_audit_token")
        evidence_input = json.dumps(
            {
                "action_name": intent.action_name,
                "action_payload": intent.action_payload,
                "audit_token": token,
            },
            sort_keys=True,
        )
        return ActionExecutionReceipt(
            status=ActionStatus.SUCCESS,
            evidence_payload={
                "execution_domain": self.execution_domain,
                "cloud_audit_token": token,
                "cloud_response_hash": hashlib.sha256(
                    evidence_input.encode("utf-8")
                ).hexdigest(),
            },
        )


def build_default_cloud_browser_executor() -> CloudBrowserExecutor:
    return CloudBrowserExecutor(
        plugin_id="execution-browser-cloud",
        version="1.0.0",
        is_concurrency_safe=False,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["execution_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
