from __future__ import annotations
"""
Kernel Overview Thin Adapter — Web Console Layer.

ARCHITECTURE ROLE:
1. Thin Facade: Directs API requests to core domain services (KernelService).
2. Zero Business Logic: Strictly prohibited from implementing state aggregation rules or audit-event analysis.
3. Responsibility:
   - [Query Condition Preparation]: Preparing session and weight context for core snapshotting.
   - [Result Splicing]: Mapping core runtime snapshots into the RuntimeOverviewPayload API contract.

DECOUPLING POLICY (Zentex Codex §2):
This module must remain a 'Logic-Free Zone'. Any evolution of session snapshot logic, 
audit-event serialization rules, or aggregate state derivation must be implemented in `zentex.kernel.service`.
"""
from typing import Any, Optional

from zentex.kernel.service import KernelService
from zentex.web_console.contracts.runtime import RuntimeOverviewPayload
from zentex.web_console.audit_event_serialization import serialize_audit_event
from zentex.web_console.contracts.audit_event import AuditEventPayload


def _coerce_audit_event_payload(entry: Any) -> AuditEventPayload:
    if isinstance(entry, dict):
        # Normalise timestamp to ISO string if it's a datetime object
        ts = entry.get("timestamp")
        if hasattr(ts, "isoformat"):
            entry = {**entry, "timestamp": ts.isoformat()}
        # Normalise entry_type to string (may be an Enum)
        et = entry.get("entry_type")
        if et is not None and not isinstance(et, str):
            entry = {**entry, "entry_type": str(getattr(et, "value", et))}
        return AuditEventPayload.model_validate(entry)
    return serialize_audit_event(entry)

def build_overview_payload(
    facade: KernelService,
    foundation: Optional[Any] = None,
    session_id: str = "zentex-default-session",
    weight_assembler: Optional[Any] = None,
) -> RuntimeOverviewPayload:
    """
    Thin adapter for core runtime overview.
    Zero business logic: only orchestrates delegation and result splicing.
    """
    # 1. Retrieve aggregated snapshot from core (QueryCondition/Aggregation moved to core)
    snapshot = facade.get_runtime_overview(
        session_id=session_id,
        weight_assembler=weight_assembler
    )
    
    # 2. Result Splicing (Mapping core data to UI Contract)
    recent_events = [
        _coerce_audit_event_payload(entry)
        for entry in snapshot.get("recent_entries", [])
    ]
    
    last_intervention = None
    if snapshot.get("last_intervention"):
        last_intervention = _coerce_audit_event_payload(snapshot["last_intervention"])

    weights = snapshot.get("weights") or {}
    
    return RuntimeOverviewPayload(
        runtime=snapshot.get("runtime", {}),
        session=snapshot.get("session") or {},
        working_memory=snapshot.get("working_memory", {"slots": []}),
        metacognition=snapshot.get("metacognition", {}),
        living_self_model=snapshot.get("living_self_model", {}),
        temporal_agenda=snapshot.get("temporal_agenda", {}),
        recent_events=recent_events,
        last_intervention_event=last_intervention,
        active_weight_plugin_id=weights.get("active_plugin_id"),
        weight_fallback_occurred=weights.get("fallback_occurred", False),
        weight_profile=weights.get("profile", {}),
    )
