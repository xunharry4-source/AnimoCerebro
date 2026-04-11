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


class LocalSystemExecutor(ExecutionDomainPlugin):
    execution_domain: str = "system"
    requires_cloud_audit: bool = False

    def execute_action(
        self,
        intent: ActionIntent,
        context: Dict[str, object],
    ) -> ActionExecutionReceipt:
        evidence_input = json.dumps(
            {
                "action_name": intent.action_name,
                "action_payload": intent.action_payload,
                "workspace": context.get("workspace"),
            },
            sort_keys=True,
        )
        return ActionExecutionReceipt(
            status=ActionStatus.SUCCESS,
            evidence_payload={
                "execution_domain": self.execution_domain,
                "action_hash": hashlib.sha256(evidence_input.encode("utf-8")).hexdigest(),
                "workspace": context.get("workspace"),
            },
        )


def build_default_local_system_executor() -> LocalSystemExecutor:
    return LocalSystemExecutor(
        plugin_id="execution-system-local",
        version="1.0.0",
        is_concurrency_safe=False,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["execution_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
