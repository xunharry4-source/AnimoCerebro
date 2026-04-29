from __future__ import annotations

from datetime import datetime
from typing import Any

from zentex.collaboration.collective_memory import CollectiveMemory
from zentex.collaboration.organization_protocol import (
    OrganizationCompletionReview,
    OrganizationCompletionSubmission,
    OrganizationConversationTurn,
    OrganizationForwardRecord,
    OrganizationFailureRecord,
    OrganizationGoalAnnouncement,
    OrganizationGoalClaim,
    OrganizationGoalDecline,
    OrganizationGoalProgress,
    OrganizationGoalSession,
    OrganizationGroupExperiencePacket,
    OrganizationNodeHeartbeat,
    OrganizationProtocol,
    OrganizationRecoveryRecord,
    OrganizationSkillAnnouncement,
    OrganizationTrustRecord,
)
from zentex.collaboration.experience_exchange import (
    ApplicableExperienceScope,
    ExperienceAuditEvent,
    ExperienceContaminationRecord,
    ExperienceAdoptionReview,
    ExperienceExchange,
    ExperienceExchangeConfig,
    ExperienceExchangePacket,
    ExperienceType,
    ExperienceQuarantineEntry,
    ExperienceRevocationRecord,
    ExperienceRollbackResult,
)
from zentex.collaboration.models import ConsensusProposal, DeliveryAck, PeerBrain, SharedExperience, VoteDecision


class CollaborationService:
    def __init__(
        self,
        collective_memory: CollectiveMemory | None = None,
        organization_protocol: OrganizationProtocol | None = None,
        experience_exchange: ExperienceExchange | None = None,
    ) -> None:
        self.collective_memory = collective_memory or CollectiveMemory()
        self.organization_protocol = organization_protocol or OrganizationProtocol()
        self.experience_exchange = experience_exchange or ExperienceExchange(
            ExperienceExchangeConfig(
                brain_id=self.collective_memory.local_brain_id,
                signing_key="zentex-g37-local-secret",
                verification_keys={},
            )
        )

    def register_peer(self, peer: PeerBrain) -> PeerBrain:
        return self.collective_memory.register_peer(peer)

    def get_peer(self, brain_id: str) -> PeerBrain | None:
        return self.collective_memory.get_peer(brain_id)

    def create_shared_experience(self, payload: dict[str, Any]) -> SharedExperience:
        return self.collective_memory.create_shared_experience(payload)

    def receive_shared_experience(self, experience: SharedExperience) -> SharedExperience:
        return self.collective_memory.receive_shared_experience(experience)

    def get_shared_experience(self, experience_id: str) -> SharedExperience | None:
        return self.collective_memory.get_shared_experience(experience_id)

    def broadcast_shared_experience(self, experience_id: str, target_brain_ids: list[str], transport_mode: str = "mailbox") -> list[DeliveryAck]:
        return self.collective_memory.broadcast_shared_experience(experience_id, target_brain_ids, transport_mode=transport_mode)

    def list_acks(self, message_id: str) -> list[DeliveryAck]:
        return self.collective_memory.list_acks(message_id)

    def create_consensus_proposal(self, *, topic: str, payload: dict[str, Any], quorum: int, risk_level: str = "medium") -> ConsensusProposal:
        return self.collective_memory.create_consensus_proposal(topic=topic, payload=payload, quorum=quorum, risk_level=risk_level)

    def submit_vote(self, *, proposal_id: str, voter_brain_id: str, decision: VoteDecision, rationale: str) -> ConsensusProposal:
        return self.collective_memory.submit_vote(proposal_id=proposal_id, voter_brain_id=voter_brain_id, decision=decision, rationale=rationale)

    def get_consensus_proposal(self, proposal_id: str) -> ConsensusProposal | None:
        return self.collective_memory.get_consensus_proposal(proposal_id)

    def heartbeat(self, heartbeat: OrganizationNodeHeartbeat) -> OrganizationNodeHeartbeat:
        return self.organization_protocol.heartbeat(heartbeat)

    def announce_skill(self, announcement: OrganizationSkillAnnouncement) -> OrganizationSkillAnnouncement:
        return self.organization_protocol.announce_skill(announcement)

    def query_capabilities(self, capability: str | None = None) -> list[OrganizationSkillAnnouncement]:
        return self.organization_protocol.query_capabilities(capability)

    def announce_goal(self, announcement: OrganizationGoalAnnouncement) -> OrganizationGoalSession:
        return self.organization_protocol.announce_goal(announcement)

    def claim_goal(self, claim: OrganizationGoalClaim) -> OrganizationGoalClaim:
        return self.organization_protocol.claim_goal(claim)

    def confirm_claim(self, claim_id: str, *, confirmer_brain_id: str, accepted: bool) -> OrganizationGoalClaim:
        return self.organization_protocol.confirm_claim(claim_id, confirmer_brain_id=confirmer_brain_id, accepted=accepted)

    def expire_pending_claims(self, *, now: datetime | None = None) -> list[OrganizationGoalClaim]:
        return self.organization_protocol.expire_pending_claims(now=now)

    def decline_goal(self, decline: OrganizationGoalDecline) -> OrganizationGoalDecline:
        return self.organization_protocol.decline_goal(decline)

    def record_progress(self, progress: OrganizationGoalProgress) -> OrganizationGoalProgress:
        return self.organization_protocol.record_progress(progress)

    def submit_completion(self, submission: OrganizationCompletionSubmission) -> OrganizationCompletionSubmission:
        return self.organization_protocol.submit_completion(submission)

    def review_completion(self, review: OrganizationCompletionReview) -> OrganizationCompletionReview:
        return self.organization_protocol.review_completion(review)

    def record_failure(self, failure: OrganizationFailureRecord) -> OrganizationRecoveryRecord:
        return self.organization_protocol.record_failure(failure)

    def share_group_experience(self, packet: OrganizationGroupExperiencePacket) -> OrganizationGroupExperiencePacket:
        return self.organization_protocol.share_group_experience(packet)

    def record_conversation_turn(self, turn: OrganizationConversationTurn) -> OrganizationConversationTurn:
        return self.organization_protocol.record_conversation_turn(turn)

    def forward_task(
        self,
        *,
        session_id: str,
        task_item_id: str,
        requester_brain_id: str,
        target_group_id: str,
        reason: str,
    ) -> OrganizationForwardRecord:
        return self.organization_protocol.forward_task(
            session_id=session_id,
            task_item_id=task_item_id,
            requester_brain_id=requester_brain_id,
            target_group_id=target_group_id,
            reason=reason,
        )

    def repair_orphaned_session(self, *, session_id: str, recovery_owner: str) -> OrganizationRecoveryRecord:
        return self.organization_protocol.repair_orphaned_session(session_id=session_id, recovery_owner=recovery_owner)

    def get_session(self, session_id: str) -> OrganizationGoalSession:
        return self.organization_protocol.get_session(session_id)

    def list_sessions(self) -> list[OrganizationGoalSession]:
        return self.organization_protocol.list_sessions()

    def list_trust_records(self) -> list[OrganizationTrustRecord]:
        return self.organization_protocol.list_trust_records()

    def list_declines(self, session_id: str | None = None) -> list[OrganizationGoalDecline]:
        return self.organization_protocol.list_declines(session_id)

    def list_conversation_turns(self, session_id: str | None = None) -> list[OrganizationConversationTurn]:
        return self.organization_protocol.list_conversation_turns(session_id)

    def list_forwards(self, session_id: str | None = None) -> list[OrganizationForwardRecord]:
        return self.organization_protocol.list_forwards(session_id)

    def list_audit_events(self, session_id: str | None = None) -> list[Any]:
        return self.organization_protocol.list_audit_events(session_id)

    def list_failures(self, session_id: str | None = None) -> list[OrganizationFailureRecord]:
        return self.organization_protocol.list_failures(session_id)

    def list_recoveries(self, session_id: str | None = None) -> list[OrganizationRecoveryRecord]:
        return self.organization_protocol.list_recoveries(session_id)

    def list_outcomes(self, session_id: str | None = None) -> list[Any]:
        return self.organization_protocol.list_outcomes(session_id)

    def exception_matrix(self) -> dict[str, str]:
        return self.organization_protocol.exception_matrix()

    def create_packet(
        self,
        *,
        experience_type: ExperienceType,
        payload: dict[str, Any],
        applicable_scope: ApplicableExperienceScope | None = None,
        trust_score: float = 0.5,
        risk_level: str = "low",
    ) -> ExperienceExchangePacket:
        return self.experience_exchange.create_packet(
            experience_type=experience_type,
            payload=payload,
            applicable_scope=applicable_scope,
            trust_score=trust_score,
            risk_level=risk_level,  # type: ignore[arg-type]
        )

    def receive_packet(self, packet: ExperienceExchangePacket) -> ExperienceAdoptionReview:
        return self.experience_exchange.receive_packet(packet)

    def submit_review(self, review: ExperienceAdoptionReview) -> ExperienceAdoptionReview:
        return self.experience_exchange.submit_review(review)

    def promote(self, experience_id: str, *, reviewer_id: str) -> ExperienceQuarantineEntry:
        return self.experience_exchange.promote(experience_id, reviewer_id=reviewer_id)

    def use_quarantined_experience(self, experience_id: str, *, for_prompting_only: bool = True) -> dict[str, Any]:
        return self.experience_exchange.use_quarantined_experience(experience_id, for_prompting_only=for_prompting_only)

    def record_decision_influence(
        self,
        *,
        experience_id: str,
        affected_brain_id: str,
        decision_id: str,
        patch_id: str | None = None,
    ) -> dict[str, list[str]]:
        return self.experience_exchange.record_decision_influence(
            experience_id=experience_id,
            affected_brain_id=affected_brain_id,
            decision_id=decision_id,
            patch_id=patch_id,
        )

    def mark_contamination(
        self,
        *,
        experience_id: str,
        affected_brain_ids: list[str] | None = None,
        affected_decisions: list[str] | None = None,
        affected_patches: list[str] | None = None,
    ) -> ExperienceContaminationRecord:
        return self.experience_exchange.mark_contamination(
            experience_id=experience_id,
            affected_brain_ids=affected_brain_ids,
            affected_decisions=affected_decisions,
            affected_patches=affected_patches,
        )

    def execute_rollback(self, contamination_id: str, *, rollback_scope: str = "full") -> ExperienceRollbackResult:
        return self.experience_exchange.execute_rollback(contamination_id, rollback_scope=rollback_scope)  # type: ignore[arg-type]

    def revoke_packet(self, *, experience_id: str, source_brain_id: str, reason: str) -> ExperienceRevocationRecord:
        return self.experience_exchange.revoke_packet(experience_id=experience_id, source_brain_id=source_brain_id, reason=reason)

    def list_quarantine(self) -> list[ExperienceQuarantineEntry]:
        return self.experience_exchange.list_quarantine()

    def list_adopted(self) -> list[ExperienceQuarantineEntry]:
        return self.experience_exchange.list_adopted()

    def list_reviews(self, experience_id: str | None = None) -> list[ExperienceAdoptionReview]:
        return self.experience_exchange.list_reviews(experience_id)

    def list_contamination(self) -> list[ExperienceContaminationRecord]:
        return self.experience_exchange.list_contamination()

    def list_rollbacks(self) -> list[ExperienceRollbackResult]:
        return self.experience_exchange.list_rollbacks()

    def list_revocations(self) -> list[ExperienceRevocationRecord]:
        return self.experience_exchange.list_revocations()

    def list_rejections(self) -> list[ExperienceAdoptionReview]:
        return self.experience_exchange.list_rejections()

    def list_experience_audit_events(self) -> list[ExperienceAuditEvent]:
        return self.experience_exchange.list_audit_events()


_SERVICE: CollaborationService | None = None


def get_service() -> CollaborationService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = CollaborationService()
    return _SERVICE
