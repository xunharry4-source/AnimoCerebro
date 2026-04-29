from __future__ import annotations

from typing import Any

from zentex.execution.adapters import LedgerActuatorAdapter
from zentex.execution.models import ActionExecutionReceipt, ExecutionRequest
from zentex.execution.orchestrator import ExecutionOrchestrator
from zentex.execution.router import ActuationRouter, ProtocolManifest


class ExecutionService:
    def __init__(self, orchestrator: ExecutionOrchestrator, ledger_adapter: LedgerActuatorAdapter) -> None:
        self.orchestrator = orchestrator
        self.ledger_adapter = ledger_adapter

    def execute_action(self, request: ExecutionRequest) -> ActionExecutionReceipt:
        return self.orchestrator.execute_action(request)

    def get_receipt(self, receipt_id: str) -> ActionExecutionReceipt | None:
        return self.orchestrator.get_receipt(receipt_id)

    def get_ledger_value(self, key: str) -> Any:
        return self.ledger_adapter.get_value(key)


_SERVICE: ExecutionService | None = None


def get_service() -> ExecutionService:
    global _SERVICE
    if _SERVICE is None:
        router = ActuationRouter()
        ledger_adapter = LedgerActuatorAdapter()
        router.register_adapter(ledger_adapter)
        router.register_protocol(ProtocolManifest(protocol_id="internal_agent_contract", adapter_id=ledger_adapter.adapter_id, priority=1))
        _SERVICE = ExecutionService(
            orchestrator=ExecutionOrchestrator(router=router),
            ledger_adapter=ledger_adapter,
        )
    return _SERVICE
