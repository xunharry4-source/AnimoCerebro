from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from zentex.kernel import AuditEventType


def persist_q5_model_invoked(
    store: Any,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: dict[str, Any],
) -> None:
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=AuditEventType.MODEL_PROVIDER_INVOKED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )


def persist_q5_model_completed(
    store: Any,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: dict[str, Any],
) -> None:
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=AuditEventType.MODEL_PROVIDER_COMPLETED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )
