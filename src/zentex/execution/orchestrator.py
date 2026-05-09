from __future__ import annotations

from typing import Any

from zentex.execution.models import ActionExecutionReceipt, ExecutionMode, ExecutionRequest
from zentex.execution.router import ActuationRouter
from zentex.safety.cloud_auditor import CloudAuditorClient, CloudDecisionStatus
from zentex.safety.safety_gate import RiskLevel, SafetyGate


class ExecutionOrchestrator:
    def __init__(
        self,
        *,
        router: ActuationRouter,
        safety_gate: SafetyGate | None = None,
        cloud_auditor: CloudAuditorClient | None = None,
    ) -> None:
        self.router = router
        self.safety_gate = safety_gate or SafetyGate()
        self.cloud_auditor = cloud_auditor or CloudAuditorClient()
        self._receipts: dict[str, ActionExecutionReceipt] = {}

    def execute_action(self, request: ExecutionRequest) -> ActionExecutionReceipt:
        safety_decision = self.safety_gate.validate_action(
            request.action_type,
            {
                "target": request.target,
                "parameters": request.parameters,
                "execution_mode": request.execution_mode.value,
                "execution_domain": request.execution_domain,
            },
            risk_level=RiskLevel(request.risk_level),
            context=request.context,
        )
        if not safety_decision.allowed and safety_decision.status.value != "requires_cloud_audit":
            return self._store_receipt(ActionExecutionReceipt(
                action_id=request.action_id,
                action_type=request.action_type,
                status="blocked",
                execution_mode=request.execution_mode,
                safety_decision_id=safety_decision.decision_id,
                safety_allowed=False,
                safety_status=safety_decision.status.value,
                evidence_payload={"safety_reason": safety_decision.reason},
                error_message=safety_decision.reason,
            ))

        cloud_status: str | None = None
        if (
            request.execution_mode == ExecutionMode.REAL
            and (request.requires_cloud_audit or safety_decision.status.value == "requires_cloud_audit" or request.risk_level in {"high", "critical"})
        ):
            cloud_decision = self.cloud_auditor.audit_action(
                request.action_type,
                request.parameters,
                risk_level=request.risk_level,
                context=request.context,
            )
            cloud_status = cloud_decision.status.value
            cloud_degraded = bool(cloud_decision.constraints.get("degraded_mode"))
            if cloud_decision.status != CloudDecisionStatus.APPROVED or cloud_degraded:
                error_message = cloud_decision.reason
                if cloud_degraded:
                    error_message = f"{cloud_decision.reason}; degraded cloud audit decisions cannot authorize execution"
                return self._store_receipt(ActionExecutionReceipt(
                    action_id=request.action_id,
                    action_type=request.action_type,
                    status="cloud_audit_required",
                    execution_mode=request.execution_mode,
                    safety_decision_id=safety_decision.decision_id,
                    safety_allowed=safety_decision.allowed,
                    safety_status=safety_decision.status.value,
                    cloud_decision_status=cloud_status,
                    evidence_payload={
                        "cloud_reason": cloud_decision.reason,
                        "cloud_constraints": cloud_decision.constraints,
                    },
                    error_message=error_message,
                ))

        try:
            adapter, protocol_id = self.router.route(request)
            if request.execution_mode == ExecutionMode.SIMULATE:
                evidence = adapter.simulate(request)
                status = "simulated"
                committed = False
            elif request.execution_mode == ExecutionMode.DRY_RUN:
                evidence = adapter.dry_run(request)
                status = "dry_run"
                committed = False
            else:
                evidence = adapter.execute(request)
                status = "succeeded"
                committed = True
            return self._store_receipt(ActionExecutionReceipt(
                action_id=request.action_id,
                action_type=request.action_type,
                status=status,  # type: ignore[arg-type]
                execution_mode=request.execution_mode,
                adapter_id=adapter.adapter_id,
                protocol_id=protocol_id,
                safety_decision_id=safety_decision.decision_id,
                safety_allowed=True,
                safety_status=safety_decision.status.value,
                cloud_decision_status=cloud_status,
                side_effect_committed=committed,
                evidence_payload=evidence,
            ))
        except (KeyError, ValueError, RuntimeError, OSError) as exc:
            return self._store_receipt(ActionExecutionReceipt(
                action_id=request.action_id,
                action_type=request.action_type,
                status="failed",
                execution_mode=request.execution_mode,
                safety_decision_id=safety_decision.decision_id,
                safety_allowed=safety_decision.allowed,
                safety_status=safety_decision.status.value,
                cloud_decision_status=cloud_status,
                evidence_payload={"error_type": type(exc).__name__},
                error_message=str(exc),
            ))

    def get_receipt(self, receipt_id: str) -> ActionExecutionReceipt | None:
        return self._receipts.get(receipt_id)

    def _store_receipt(self, receipt: ActionExecutionReceipt) -> ActionExecutionReceipt:
        self._receipts[receipt.receipt_id] = receipt
        return receipt
