from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from zentex.collaboration.organization_protocol import (
    OrganizationCompletionReview,
    OrganizationCompletionSubmission,
    OrganizationConversationTurn,
    OrganizationFailureRecord,
    OrganizationGoalAnnouncement,
    OrganizationGoalClaim,
    OrganizationGoalDecline,
    OrganizationGoalProgress,
    OrganizationGroupExperiencePacket,
    OrganizationNodeHeartbeat,
    OrganizationSkillAnnouncement,
)
from zentex.collaboration.experience_exchange import (
    ApplicableExperienceScope,
    ExperienceAdoptionReview,
    ExperienceExchangePacket,
    ExperienceType,
)
from zentex.collaboration.models import PeerBrain, SharedExperience, VoteDecision


router = APIRouter()


class ExperienceCreateRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    target_brain_ids: list[str] = Field(default_factory=list)
    transport_mode: str = "mailbox"


class ConsensusCreateRequest(BaseModel):
    topic: str
    payload: dict[str, Any] = Field(default_factory=dict)
    quorum: int = Field(ge=1)
    risk_level: str = "medium"


class VoteCreateRequest(BaseModel):
    voter_brain_id: str
    decision: VoteDecision
    rationale: str


class ClaimConfirmationRequest(BaseModel):
    confirmer_brain_id: str
    accepted: bool


class ForwardRequest(BaseModel):
    session_id: str
    task_item_id: str
    requester_brain_id: str
    target_group_id: str
    reason: str


class RepairOrphanRequest(BaseModel):
    session_id: str
    recovery_owner: str


class PacketCreateRequest(BaseModel):
    experience_type: ExperienceType
    payload: dict[str, Any] = Field(default_factory=dict)
    applicable_scope: ApplicableExperienceScope = Field(default_factory=ApplicableExperienceScope)
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_level: str = "low"


class PromoteRequest(BaseModel):
    reviewer_id: str


class UseQuarantineRequest(BaseModel):
    for_prompting_only: bool = True


class DecisionInfluenceRequest(BaseModel):
    affected_brain_id: str
    decision_id: str
    patch_id: str | None = None


class ContaminationRequest(BaseModel):
    affected_brain_ids: list[str] = Field(default_factory=list)
    affected_decisions: list[str] = Field(default_factory=list)
    affected_patches: list[str] = Field(default_factory=list)


class RollbackRequest(BaseModel):
    rollback_scope: str = "full"


class RevocationRequest(BaseModel):
    source_brain_id: str
    reason: str


def _get_service(request: Request):
    service = getattr(request.app.state, "collaboration_service", None)
    if service is not None:
        return service
    from zentex.collaboration.service import get_service

    service = get_service()
    request.app.state.collaboration_service = service
    return service


@router.post("/collaboration/peers")
def register_peer(peer: PeerBrain, request: Request) -> PeerBrain:
    return _get_service(request).register_peer(peer)


@router.get("/collaboration/peers/{brain_id}")
def get_peer(brain_id: str, request: Request) -> PeerBrain:
    peer = _get_service(request).get_peer(brain_id)
    if peer is None:
        raise HTTPException(status_code=404, detail=f"Peer {brain_id} not found")
    return peer


@router.post("/collaboration/experiences")
def create_experience(payload: ExperienceCreateRequest, request: Request) -> dict[str, Any]:
    service = _get_service(request)
    experience = service.create_shared_experience(payload.payload)
    acks = []
    if payload.target_brain_ids:
        acks = service.broadcast_shared_experience(
            experience.experience_id,
            payload.target_brain_ids,
            payload.transport_mode,
        )
    return {
        "experience": experience,
        "acks": acks,
    }


@router.post("/collaboration/experiences/receive")
def receive_experience(experience: SharedExperience, request: Request) -> SharedExperience:
    try:
        return _get_service(request).receive_shared_experience(experience)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/collaboration/experiences/{experience_id}")
def get_experience(experience_id: str, request: Request) -> SharedExperience:
    experience = _get_service(request).get_shared_experience(experience_id)
    if experience is None:
        raise HTTPException(status_code=404, detail=f"SharedExperience {experience_id} not found")
    return experience


@router.get("/collaboration/acks/{message_id}")
def list_acks(message_id: str, request: Request) -> list[Any]:
    return _get_service(request).list_acks(message_id)


@router.post("/collaboration/proposals")
def create_proposal(payload: ConsensusCreateRequest, request: Request):
    return _get_service(request).create_consensus_proposal(
        topic=payload.topic,
        payload=payload.payload,
        quorum=payload.quorum,
        risk_level=payload.risk_level,
    )


@router.get("/collaboration/proposals/{proposal_id}")
def get_proposal(proposal_id: str, request: Request):
    proposal = _get_service(request).get_consensus_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"ConsensusProposal {proposal_id} not found")
    return proposal


@router.post("/collaboration/proposals/{proposal_id}/votes")
def submit_vote(proposal_id: str, payload: VoteCreateRequest, request: Request):
    try:
        return _get_service(request).submit_vote(
            proposal_id=proposal_id,
            voter_brain_id=payload.voter_brain_id,
            decision=payload.decision,
            rationale=payload.rationale,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collaboration/g36/heartbeats")
def heartbeat(payload: OrganizationNodeHeartbeat, request: Request) -> dict[str, Any]:
    return _get_service(request).heartbeat(payload).model_dump(mode="json")


@router.post("/collaboration/g36/skills")
def announce_skill(payload: OrganizationSkillAnnouncement, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).announce_skill(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/collaboration/g36/capabilities")
def query_capabilities(request: Request, capability: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).query_capabilities(capability)]


@router.post("/collaboration/g36/goals")
def announce_goal(payload: OrganizationGoalAnnouncement, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).announce_goal(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/collaboration/g36/goals")
def list_sessions(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_sessions()]


@router.get("/collaboration/g36/goals/{session_id}")
def get_session(session_id: str, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).get_session(session_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/collaboration/g36/claims")
def claim_goal(payload: OrganizationGoalClaim, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).claim_goal(payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/collaboration/g36/claims/{claim_id}/confirm")
def confirm_claim(claim_id: str, payload: ClaimConfirmationRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).confirm_claim(
            claim_id,
            confirmer_brain_id=payload.confirmer_brain_id,
            accepted=payload.accepted,
        ).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/collaboration/g36/claims/expire")
def expire_pending_claims(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).expire_pending_claims()]


@router.post("/collaboration/g36/declines")
def decline_goal(payload: OrganizationGoalDecline, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).decline_goal(payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/collaboration/g36/declines")
def list_declines(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_declines(session_id)]


@router.post("/collaboration/g36/progress")
def record_progress(payload: OrganizationGoalProgress, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).record_progress(payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/collaboration/g36/completions")
def submit_completion(payload: OrganizationCompletionSubmission, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).submit_completion(payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/collaboration/g36/reviews")
def review_completion(payload: OrganizationCompletionReview, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).review_completion(payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/collaboration/g36/failures")
def record_failure(payload: OrganizationFailureRecord, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).record_failure(payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/collaboration/g36/conversation-turns")
def record_conversation_turn(payload: OrganizationConversationTurn, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).record_conversation_turn(payload).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/collaboration/g36/conversation-turns")
def list_conversation_turns(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_conversation_turns(session_id)]


@router.post("/collaboration/g36/forwards")
def forward_task(payload: ForwardRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).forward_task(
            session_id=payload.session_id,
            task_item_id=payload.task_item_id,
            requester_brain_id=payload.requester_brain_id,
            target_group_id=payload.target_group_id,
            reason=payload.reason,
        ).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/collaboration/g36/forwards")
def list_forwards(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_forwards(session_id)]


@router.post("/collaboration/g36/orphaned-session-repairs")
def repair_orphaned_session(payload: RepairOrphanRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).repair_orphaned_session(
            session_id=payload.session_id,
            recovery_owner=payload.recovery_owner,
        ).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/collaboration/g36/failures")
def list_failures(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_failures(session_id)]


@router.get("/collaboration/g36/recoveries")
def list_recoveries(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_recoveries(session_id)]


@router.post("/collaboration/g36/group-experiences")
def share_group_experience(payload: OrganizationGroupExperiencePacket, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).share_group_experience(payload).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/collaboration/g36/trust")
def list_trust_records(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_trust_records()]


@router.get("/collaboration/g36/outcomes")
def list_outcomes(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_outcomes(session_id)]


@router.get("/collaboration/g36/audit")
def list_audit(request: Request, session_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_audit_events(session_id)]


@router.get("/collaboration/g36/exception-matrix")
def exception_matrix(request: Request) -> dict[str, str]:
    return _get_service(request).exception_matrix()


@router.post("/collaboration/g37/packets")
def create_packet(payload: PacketCreateRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).create_packet(
            experience_type=payload.experience_type,
            payload=payload.payload,
            applicable_scope=payload.applicable_scope,
            trust_score=payload.trust_score,
            risk_level=payload.risk_level,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/collaboration/g37/packets/receive")
def receive_packet(payload: ExperienceExchangePacket, request: Request) -> dict[str, Any]:
    return _get_service(request).receive_packet(payload).model_dump(mode="json")


@router.post("/collaboration/g37/reviews")
def submit_review(payload: ExperienceAdoptionReview, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).submit_review(payload).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/collaboration/g37/quarantine/{experience_id}/promote")
def promote(experience_id: str, payload: PromoteRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).promote(experience_id, reviewer_id=payload.reviewer_id).model_dump(mode="json")
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/collaboration/g37/quarantine/{experience_id}/use")
def use_quarantined_experience(experience_id: str, payload: UseQuarantineRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).use_quarantined_experience(
            experience_id,
            for_prompting_only=payload.for_prompting_only,
        )
    except (KeyError, ValueError) as exc:
        status = 404 if isinstance(exc, KeyError) else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/collaboration/g37/quarantine")
def list_quarantine(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_quarantine()]


@router.get("/collaboration/g37/adopted")
def list_adopted(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_adopted()]


@router.get("/collaboration/g37/reviews")
def list_reviews(request: Request, experience_id: str | None = None) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_reviews(experience_id)]


@router.post("/collaboration/g37/experiences/{experience_id}/decision-influence")
def record_decision_influence(experience_id: str, payload: DecisionInfluenceRequest, request: Request) -> dict[str, list[str]]:
    try:
        return _get_service(request).record_decision_influence(
            experience_id=experience_id,
            affected_brain_id=payload.affected_brain_id,
            decision_id=payload.decision_id,
            patch_id=payload.patch_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/collaboration/g37/experiences/{experience_id}/contamination")
def mark_contamination(experience_id: str, payload: ContaminationRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).mark_contamination(
            experience_id=experience_id,
            affected_brain_ids=payload.affected_brain_ids,
            affected_decisions=payload.affected_decisions,
            affected_patches=payload.affected_patches,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/collaboration/g37/contamination/{contamination_id}/rollback")
def execute_rollback(contamination_id: str, payload: RollbackRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).execute_rollback(
            contamination_id,
            rollback_scope=payload.rollback_scope,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/collaboration/g37/contamination")
def list_contamination(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_contamination()]


@router.get("/collaboration/g37/rollbacks")
def list_rollbacks(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_rollbacks()]


@router.post("/collaboration/g37/experiences/{experience_id}/revoke")
def revoke_packet(experience_id: str, payload: RevocationRequest, request: Request) -> dict[str, Any]:
    try:
        return _get_service(request).revoke_packet(
            experience_id=experience_id,
            source_brain_id=payload.source_brain_id,
            reason=payload.reason,
        ).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/collaboration/g37/revocations")
def list_revocations(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_revocations()]


@router.get("/collaboration/g37/rejections")
def list_rejections(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_rejections()]


@router.get("/collaboration/g37/audit")
def list_audit(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _get_service(request).list_experience_audit_events()]
