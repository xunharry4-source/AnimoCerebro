"""Web API for G29 managed memory records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from zentex.memory.managed_memory import ManagedMemoryRecord, SQLiteManagedMemoryStore

router = APIRouter(prefix="/managed-memory", tags=["managed-memory"])


class GovernanceUpdateRequest(BaseModel):
    """Memory governance update payload."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    visibility: str | None = None
    trust_level: str | None = None
    correction_note: str | None = None
    reason: str


def _store(request: Request) -> SQLiteManagedMemoryStore:
    store = getattr(request.app.state, "managed_memory_store", None)
    if store is None:
        store = SQLiteManagedMemoryStore()
        request.app.state.managed_memory_store = store
    return store


@router.post("/records")
def remember(payload: ManagedMemoryRecord, request: Request) -> dict[str, object]:
    """Write a memory and return the persisted record."""

    return _store(request).remember(payload).model_dump(mode="json")


@router.get("/records")
def query_records(
    request: Request,
    query_text: str = Query(min_length=1),
    topic: str | None = None,
    role: str | None = None,
    risk_level: str | None = None,
) -> list[dict[str, object]]:
    """Query memories with structured filters and ranking explanations."""

    return [
        row.model_dump(mode="json")
        for row in _store(request).query(query_text=query_text, topic=topic, role=role, risk_level=risk_level)
    ]


@router.get("/records/{memory_id}")
def get_record(memory_id: str, request: Request) -> dict[str, object]:
    """Return one memory record."""

    record = _store(request).get(memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found"})
    return record.model_dump(mode="json")


@router.patch("/records/{memory_id}/governance")
def update_governance(memory_id: str, payload: GovernanceUpdateRequest, request: Request) -> dict[str, object]:
    """Update governance fields and return the modified record."""

    try:
        record = _store(request).update_governance(
            memory_id,
            status=payload.status,
            visibility=payload.visibility,
            trust_level=payload.trust_level,
            correction_note=payload.correction_note,
            reason=payload.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "memory_not_found"}) from exc
    return record.model_dump(mode="json")


@router.get("/records/{memory_id}/audit")
def list_audit(memory_id: str, request: Request) -> list[dict[str, object]]:
    """Return memory audit events."""

    return [row.model_dump(mode="json") for row in _store(request).list_audit_events(memory_id)]
