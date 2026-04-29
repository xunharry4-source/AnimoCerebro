from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.audit.brain_transcript_chain import (
    BrainTranscriptChainStore,
    CrossBrainTraceMergeRequest,
    TraceReplayDiffRequest,
    TraceSearchFilters,
    TraceSpan,
    TraceSpanAppendResult,
    build_default_chain_store,
)
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType


router = APIRouter(prefix="/brain-transcript-chain", tags=["brain-transcript-chain"])


def _chain_store(request: Request) -> BrainTranscriptChainStore:
    store = getattr(request.app.state, "brain_transcript_chain_store", None)
    if store is None:
        store = build_default_chain_store()
        request.app.state.brain_transcript_chain_store = store
    if not isinstance(store, BrainTranscriptChainStore):
        raise HTTPException(status_code=503, detail="BrainTranscriptChainStore is unavailable")
    return store


def _transcript_store(request: Request) -> Any:
    return getattr(request.app.state, "transcript_store", None)


def _write_span_audit(request: Request, result: TraceSpanAppendResult) -> None:
    if result.idempotent:
        return
    store = _transcript_store(request)
    if store is None or not callable(getattr(store, "write_entry", None)):
        raise HTTPException(status_code=503, detail="BrainTranscriptStore is unavailable")
    span = result.span
    store.write_entry(
        session_id=span.session_id or "brain-transcript-chain",
        turn_id=span.turn_id or span.span_id,
        entry_type=BrainTranscriptEntryType.FLOW_AUDIT,
        timestamp=datetime.now(timezone.utc),
        source="brain.transcript.chain",
        trace_id=span.trace_id,
        payload={
            "event_type": "brain_transcript_chain_span_appended",
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "event_type_value": span.event_type.value,
            "causal_parent_id": span.causal_parent_id,
            "origin_trace_id": span.origin_trace_id,
            "risk_level": span.risk_level,
            "blocked": span.blocked,
        },
    )


@router.post("/spans", response_model=TraceSpanAppendResult)
def append_chain_span(payload: TraceSpan, request: Request) -> TraceSpanAppendResult:
    try:
        store = _transcript_store(request)
        if store is None or not callable(getattr(store, "write_entry", None)):
            raise HTTPException(status_code=503, detail="BrainTranscriptStore is unavailable")
        result = _chain_store(request).append_span(payload)
        _write_span_audit(request, result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/traces/{trace_id}")
def get_trace_chain(trace_id: str, request: Request) -> dict[str, Any]:
    try:
        return _chain_store(request).get_trace(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/spans/{span_id}/descendants")
def get_span_descendants(span_id: str, request: Request) -> dict[str, Any]:
    try:
        return _chain_store(request).get_span_descendants(span_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/replay/{trace_id}")
def replay_trace(trace_id: str, request: Request) -> dict[str, Any]:
    try:
        return _chain_store(request).replay(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/search")
def search_trace_chains(
    request: Request,
    trace_id: str | None = None,
    origin_trace_id: str | None = None,
    session_id: str | None = None,
    decision_type: str | None = None,
    risk_level: str | None = None,
    started_from: str | None = None,
    started_to: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    filters = TraceSearchFilters(
        trace_id=trace_id,
        origin_trace_id=origin_trace_id,
        session_id=session_id,
        decision_type=decision_type,
        risk_level=risk_level,
        started_from=started_from,
        started_to=started_to,
        limit=limit,
    )
    return _chain_store(request).search(filters)


@router.post("/cross-brain-merge")
def cross_brain_trace_merge(payload: CrossBrainTraceMergeRequest, request: Request) -> dict[str, Any]:
    try:
        return _chain_store(request).cross_brain_trace_merge(payload)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/diff")
def diff_trace_replays(payload: TraceReplayDiffRequest, request: Request) -> dict[str, Any]:
    try:
        return _chain_store(request).diff_traces(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
