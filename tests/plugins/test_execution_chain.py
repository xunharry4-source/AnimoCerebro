from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from plugins.execution.base_executor_chain import (  # noqa: E402
    CloudBrowserExecutor,
    ExecutionOrchestrator,
    LocalSystemExecutor,
)
from zentex.core.execution_spec import (  # noqa: E402
    ActionExecutionReceipt,
    ActionIntent,
    ActionStatus,
    CloudAuditAuthError,
    CloudAuditDecision,
    SafetyDecision,
    SecurityBlockError,
)
from zentex.core.plugin_base import (  # noqa: E402
    PluginHealthStatus,
    PluginLifecycleStatus,
)


def _build_local_plugin() -> LocalSystemExecutor:
    return LocalSystemExecutor(
        plugin_id="execution-system-local",
        version="1.0.0",
        is_concurrency_safe=False,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["execution_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


def _build_cloud_plugin() -> CloudBrowserExecutor:
    return CloudBrowserExecutor(
        plugin_id="execution-browser-cloud",
        version="1.0.0",
        is_concurrency_safe=False,
        status=PluginLifecycleStatus.CANDIDATE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["execution_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


def test_safety_gate_blocks_high_risk_intent_before_execution() -> None:
    plugin = _build_local_plugin()
    plugin_execute = Mock(wraps=plugin.execute_action)
    object.__setattr__(plugin, "execute_action", plugin_execute)

    safety_gate = Mock(
        check=Mock(return_value=SafetyDecision(allowed=False, reason="critical redline"))
    )
    cloud_audit_client = Mock(
        verify=Mock(
            return_value=CloudAuditDecision(
                verified=True,
                audit_token="signed-token",
                reason="verified",
            )
        )
    )
    orchestrator = ExecutionOrchestrator(
        safety_gate=safety_gate,
        cloud_audit_client=cloud_audit_client,
    )

    with pytest.raises(SecurityBlockError):
        orchestrator.execute(
            plugin=plugin,
            intent=ActionIntent(
                action_name="delete_system_files",
                action_payload={"path": "/"},
                risk_level="critical",
            ),
            context={"workspace": "/tmp"},
        )

    plugin_execute.assert_not_called()


def test_cloud_audit_missing_token_blocks_execution() -> None:
    plugin = _build_cloud_plugin()
    plugin_execute = Mock(wraps=plugin.execute_action)
    object.__setattr__(plugin, "execute_action", plugin_execute)

    orchestrator = ExecutionOrchestrator(
        safety_gate=Mock(
            check=Mock(return_value=SafetyDecision(allowed=True, reason="ok"))
        ),
        cloud_audit_client=Mock(
            verify=Mock(
                return_value=CloudAuditDecision(
                    verified=False,
                    audit_token=None,
                    reason="missing signed token",
                )
            )
        ),
    )

    with pytest.raises(CloudAuditAuthError):
        orchestrator.execute(
            plugin=plugin,
            intent=ActionIntent(
                action_name="browser_click",
                action_payload={"selector": "#submit"},
                risk_level="medium",
            ),
            context={"workspace": "/tmp"},
        )

    plugin_execute.assert_not_called()


def test_valid_low_risk_action_returns_structured_receipt() -> None:
    plugin = _build_local_plugin()
    orchestrator = ExecutionOrchestrator(
        safety_gate=Mock(
            check=Mock(return_value=SafetyDecision(allowed=True, reason="ok"))
        ),
        cloud_audit_client=Mock(
            verify=Mock(
                return_value=CloudAuditDecision(
                    verified=True,
                    audit_token="token",
                    reason="verified",
                )
            )
        ),
    )

    receipt = orchestrator.execute(
        plugin=plugin,
        intent=ActionIntent(
            action_name="write_status_file",
            action_payload={"path": "/tmp/status.txt", "content": "ok"},
            risk_level="low",
        ),
        context={"workspace": "/tmp"},
    )

    validated = ActionExecutionReceipt.model_validate(receipt)
    assert validated.status == ActionStatus.SUCCESS
    assert validated.evidence_payload["execution_domain"] == "system"
    assert isinstance(validated.evidence_payload["action_hash"], str)
