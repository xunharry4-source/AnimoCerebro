from __future__ import annotations

from typing import Any, Protocol

from zentex.execution.models import ExecutionRequest


class ActuatorAdapter(Protocol):
    adapter_id: str
    execution_domain: str
    supported_action_types: set[str]

    def can_execute(self, request: ExecutionRequest) -> bool:
        ...

    def simulate(self, request: ExecutionRequest) -> dict[str, Any]:
        ...

    def dry_run(self, request: ExecutionRequest) -> dict[str, Any]:
        ...

    def execute(self, request: ExecutionRequest) -> dict[str, Any]:
        ...


class LedgerActuatorAdapter:
    adapter_id = "ledger_adapter"
    execution_domain = "ledger"
    supported_action_types = {"ledger_set"}

    def __init__(self) -> None:
        self._ledger: dict[str, Any] = {}

    def can_execute(self, request: ExecutionRequest) -> bool:
        return request.action_type in self.supported_action_types and request.execution_domain == self.execution_domain

    def simulate(self, request: ExecutionRequest) -> dict[str, Any]:
        key = self._extract_key(request)
        return {"planned_key": key, "would_write": True, "existing_value": self._ledger.get(key)}

    def dry_run(self, request: ExecutionRequest) -> dict[str, Any]:
        key = self._extract_key(request)
        return {"validated_key": key, "validated_value": request.parameters.get("value"), "side_effect": "not_committed"}

    def execute(self, request: ExecutionRequest) -> dict[str, Any]:
        key = self._extract_key(request)
        value = request.parameters.get("value")
        before = self._ledger.get(key)
        self._ledger[key] = value
        return {"key": key, "before": before, "after": value, "ledger_size": len(self._ledger)}

    def get_value(self, key: str) -> Any:
        return self._ledger.get(key)

    def _extract_key(self, request: ExecutionRequest) -> str:
        key = str(request.parameters.get("key") or request.target or "").strip()
        if not key:
            raise ValueError("ledger_set requires parameters.key or target")
        return key
