from __future__ import annotations

from dataclasses import dataclass

from zentex.execution.adapters import ActuatorAdapter
from zentex.execution.models import ExecutionRequest


@dataclass(frozen=True)
class ProtocolManifest:
    protocol_id: str
    adapter_id: str
    priority: int = 100


class ActuationRouter:
    def __init__(self) -> None:
        self._adapters: dict[str, ActuatorAdapter] = {}
        self._protocols: dict[str, ProtocolManifest] = {}

    def register_adapter(self, adapter: ActuatorAdapter) -> None:
        self._adapters[adapter.adapter_id] = adapter

    def register_protocol(self, protocol: ProtocolManifest) -> None:
        if protocol.adapter_id not in self._adapters:
            raise ValueError(f"Protocol {protocol.protocol_id} references unknown adapter {protocol.adapter_id}")
        self._protocols[protocol.protocol_id] = protocol

    def route(self, request: ExecutionRequest) -> tuple[ActuatorAdapter, str | None]:
        if request.protocol_id:
            protocol = self._protocols.get(request.protocol_id)
            if protocol is None:
                raise KeyError(f"Protocol {request.protocol_id} is not registered")
            adapter = self._adapters[protocol.adapter_id]
            if not adapter.can_execute(request):
                raise ValueError(f"Adapter {adapter.adapter_id} cannot execute action {request.action_type}")
            return adapter, protocol.protocol_id

        candidates = [
            adapter
            for adapter in self._adapters.values()
            if adapter.can_execute(request)
        ]
        if not candidates:
            raise KeyError(f"No actuator adapter can execute {request.action_type} in domain {request.execution_domain}")
        return candidates[0], None
