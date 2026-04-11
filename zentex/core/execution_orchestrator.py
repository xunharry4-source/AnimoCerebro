from __future__ import annotations

"""Execution security boundary utilities.

These classes implement the mandatory safety/audit protocol for execution-domain
plugins. They are framework-level components, not plugins themselves.
"""

from typing import Dict

from zentex.core.execution_spec import (
    ActionExecutionReceipt,
    ActionIntent,
    CloudAuditAuthError,
    CloudAuditClient,
    CloudAuditDecision,
    ExecutionDomainPlugin,
    SafetyDecision,
    SafetyGate,
    SecurityBlockError,
)


class StaticSafetyGate(SafetyGate):
    """Simple deterministic safety gate used for execution-domain enforcement."""

    def check(
        self,
        intent: ActionIntent,
        context: Dict[str, object],
        plugin: ExecutionDomainPlugin,
    ) -> SafetyDecision:
        forbidden_actions = {
            "delete_system_files",
            "format_disk",
            "execute_shell",
            "open_untrusted_browser_automation",
        }
        if intent.action_name in forbidden_actions or intent.risk_level.lower() == "critical":
            return SafetyDecision(
                allowed=False,
                reason="intent hit execution redline",
            )
        return SafetyDecision(allowed=True, reason="intent passed safety gate")


class StaticCloudAuditClient(CloudAuditClient):
    """Simple cloud-audit verifier backed by explicit signed token presence."""

    def verify(
        self,
        intent: ActionIntent,
        context: Dict[str, object],
        plugin: ExecutionDomainPlugin,
    ) -> CloudAuditDecision:
        token = context.get("cloud_audit_token")
        if isinstance(token, str) and token.strip():
            return CloudAuditDecision(
                verified=True,
                audit_token=token,
                reason="cloud audit token verified",
            )
        return CloudAuditDecision(
            verified=False,
            audit_token=None,
            reason="missing cloud audit token",
        )


class ExecutionOrchestrator:
    """
    Mandatory execution security boundary.

    Hard order:
    1. safety gate check
    2. cloud audit verification when required
    3. concrete domain execution
    4. receipt validation with evidence
    """

    def __init__(
        self,
        *,
        safety_gate: SafetyGate,
        cloud_audit_client: CloudAuditClient,
    ) -> None:
        self.safety_gate = safety_gate
        self.cloud_audit_client = cloud_audit_client

    def execute(
        self,
        plugin: ExecutionDomainPlugin,
        intent: ActionIntent,
        context: Dict[str, object],
    ) -> ActionExecutionReceipt:
        decision = self.safety_gate.check(intent=intent, context=context, plugin=plugin)
        if not decision.allowed:
            raise SecurityBlockError(f"Execution blocked by safety gate: {decision.reason}")

        if plugin.requires_cloud_audit:
            audit_decision = self.cloud_audit_client.verify(
                intent=intent,
                context=context,
                plugin=plugin,
            )
            if not audit_decision.verified or not audit_decision.audit_token:
                raise CloudAuditAuthError(
                    f"Execution blocked by cloud audit: {audit_decision.reason}"
                )

            context = {**context, "cloud_audit_token": audit_decision.audit_token}

        receipt = plugin.execute_action(intent=intent, context=context)
        validated_receipt = ActionExecutionReceipt.model_validate(receipt)
        if not validated_receipt.evidence_payload:
            raise ValueError("ActionExecutionReceipt must include evidence_payload")
        return validated_receipt


def build_default_execution_orchestrator() -> ExecutionOrchestrator:
    return ExecutionOrchestrator(
        safety_gate=StaticSafetyGate(),
        cloud_audit_client=StaticCloudAuditClient(),
    )
