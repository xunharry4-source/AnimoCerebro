from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from zentex.collaboration.social_communication import (
    CollectiveDomainMapGossip,
    CooperationWillingnessSignal,
    InteractionHistoryRecord,
    SocialCommunicationRuntime,
    SocialPresenceSignal,
    SocialRoutingRequest,
    build_default_social_communication_runtime,
)
from zentex.kernel.state_domain.brain_transcript_models import BrainTranscriptEntryType


router = APIRouter(prefix="/collaboration/social", tags=["collaboration-social"])


def _runtime(request: Request) -> SocialCommunicationRuntime:
    runtime = getattr(request.app.state, "social_communication_runtime", None)
    if runtime is None:
        runtime = build_default_social_communication_runtime()
        request.app.state.social_communication_runtime = runtime
    if not isinstance(runtime, SocialCommunicationRuntime):
        raise HTTPException(status_code=503, detail="SocialCommunicationRuntime is unavailable")
    return runtime


def _write_audit(request: Request, event_type: str, payload: dict[str, Any], trace_id: str) -> None:
    store = getattr(request.app.state, "transcript_store", None)
    if store is None or not callable(getattr(store, "write_entry", None)):
        raise HTTPException(status_code=503, detail="BrainTranscriptStore is unavailable")
    store.write_entry(
        session_id="collaboration-social",
        turn_id=trace_id,
        entry_type=BrainTranscriptEntryType.FLOW_AUDIT,
        source="collaboration.social_communication",
        trace_id=trace_id,
        payload={
            "event_type": event_type,
            **payload,
        },
    )


@router.post("/interactions")
def record_social_interaction(payload: InteractionHistoryRecord, request: Request) -> dict[str, Any]:
    result = _runtime(request).record_interaction(payload)
    _write_audit(
        request,
        "social_interaction_recorded",
        {
            "brain_id": payload.brain_id,
            "domain": payload.domain,
            "task_id": payload.task_id,
            "outcome": payload.outcome.value,
            "trust_score": result["trust_score"],
        },
        payload.interaction_id,
    )
    return result


@router.get("/interactions")
def list_social_interactions(
    request: Request,
    brain_id: str | None = None,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in _runtime(request).list_interactions(brain_id, domain)]


@router.get("/trust")
def get_social_trust_score(request: Request, brain_id: str, domain: str) -> dict[str, Any]:
    return _runtime(request).trust_score(brain_id, domain).model_dump(mode="json")


@router.get("/reputation/{brain_id}")
def get_brain_reputation_profile(brain_id: str, request: Request) -> dict[str, Any]:
    return _runtime(request).reputation(brain_id).model_dump(mode="json")


@router.post("/presence")
def broadcast_social_presence(payload: SocialPresenceSignal, request: Request) -> dict[str, Any]:
    try:
        signal = _runtime(request).broadcast_presence(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _write_audit(
        request,
        "social_presence_broadcast",
        {
            "brain_id": signal.brain_id,
            "available_domains": signal.available_domains,
            "current_load_level": signal.current_load_level,
            "version": signal.version,
        },
        f"presence:{signal.brain_id}:{signal.version}",
    )
    return signal.model_dump(mode="json")


@router.get("/presence/{brain_id}")
def get_social_presence(brain_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).get_presence(brain_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"presence not found: {brain_id}") from exc


@router.post("/willingness")
def publish_cooperation_willingness(payload: CooperationWillingnessSignal, request: Request) -> dict[str, Any]:
    try:
        signal = _runtime(request).publish_willingness(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _write_audit(
        request,
        "social_willingness_published",
        {
            "brain_id": signal.brain_id,
            "unavailable_domains": signal.unavailable_domains,
            "risk_ceiling": signal.risk_ceiling,
            "valid_until": signal.valid_until,
        },
        f"willingness:{signal.brain_id}",
    )
    return signal.model_dump(mode="json")


@router.get("/domain-map")
def get_collective_domain_map(request: Request, domain: str | None = None) -> dict[str, Any]:
    return _runtime(request).domain_map(domain)


@router.post("/domain-map/gossip")
def merge_collective_domain_map_gossip(payload: CollectiveDomainMapGossip, request: Request) -> dict[str, Any]:
    try:
        result = _runtime(request).merge_domain_map_gossip(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result_payload = result.model_dump(mode="json")
    _write_audit(
        request,
        "social_domain_map_gossip_merged",
        result_payload,
        f"domain-map-gossip:{result.source_brain_id}:{result.gossip_version}",
    )
    return result_payload


@router.post("/route")
def recommend_social_route(payload: SocialRoutingRequest, request: Request) -> dict[str, Any]:
    try:
        result = _runtime(request).route(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result_payload = result.model_dump(mode="json")
    _write_audit(
        request,
        "social_route_recommended",
        {
            "task_domain": result.task_domain,
            "candidate_count": len(result.candidates),
            "rejected_count": len(result.rejected_candidates),
            "recommendation_only": result.recommendation_only,
        },
        result.route_id,
    )
    return result_payload


@router.get("/audit")
def list_social_audit(request: Request) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in _runtime(request).list_audit()]
