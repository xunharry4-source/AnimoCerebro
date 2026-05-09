from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from zentex.collaboration.models import (
    AckStatus,
    ConsensusProposal,
    ConsensusStatus,
    ConsensusVote,
    DeliveryAck,
    PeerBrain,
    SharedExperience,
    VoteDecision,
)
from zentex.collaboration.transports import ExperienceTransport, HttpExperienceTransport, MailboxTransport


class CollectiveMemory:
    def __init__(self, *, local_brain_id: str = "zentex.local", local_secret: str = "zentex-local-secret") -> None:
        if len(local_secret) < 8:
            raise ValueError("local_secret must be at least 8 characters")
        self.local_brain_id = local_brain_id
        self._local_secret = local_secret
        self._peers: dict[str, PeerBrain] = {
            local_brain_id: PeerBrain(brain_id=local_brain_id, shared_secret=local_secret)
        }
        self._experiences: dict[str, SharedExperience] = {}
        self._acks: dict[str, DeliveryAck] = {}
        self._proposals: dict[str, ConsensusProposal] = {}
        self._votes: dict[str, dict[str, ConsensusVote]] = {}
        self.mailbox_transport = MailboxTransport()
        self.http_transport = HttpExperienceTransport()

    def register_peer(self, peer: PeerBrain) -> PeerBrain:
        self._peers[peer.brain_id] = peer
        return peer

    def get_peer(self, brain_id: str) -> PeerBrain | None:
        return self._peers.get(brain_id)

    def list_active_peers(self) -> list[PeerBrain]:
        return [peer for peer in self._peers.values() if peer.active]

    def create_shared_experience(self, payload: dict[str, Any]) -> SharedExperience:
        unsigned = {
            "source_brain_id": self.local_brain_id,
            "payload": payload,
        }
        signature = self._sign(unsigned, self._local_secret)
        experience = SharedExperience(
            source_brain_id=self.local_brain_id,
            payload=payload,
            signature=signature,
        )
        signed = experience.model_dump(mode="json", exclude={"signature", "accepted_to_core_memory", "quarantine_reason"})
        experience.signature = self._sign(signed, self._local_secret)
        return self.receive_shared_experience(experience)

    def receive_shared_experience(self, experience: SharedExperience) -> SharedExperience:
        if experience.experience_id in self._experiences:
            return self._experiences[experience.experience_id]
        peer = self._peers.get(experience.source_brain_id)
        if peer is None:
            raise ValueError(f"Unknown source brain: {experience.source_brain_id}")
        if not self.verify_shared_experience(experience):
            raise ValueError("SharedExperience signature verification failed")
        accepted = peer.trust_score >= 0.5 and peer.active
        persisted = experience.model_copy(
            update={
                "accepted_to_core_memory": accepted,
                "quarantine_reason": None if accepted else "source trust below core-memory threshold or inactive",
            }
        )
        self._experiences[persisted.experience_id] = persisted
        return persisted

    def get_shared_experience(self, experience_id: str) -> SharedExperience | None:
        return self._experiences.get(experience_id)

    def broadcast_shared_experience(
        self,
        experience_id: str,
        target_brain_ids: list[str],
        *,
        transport_mode: str = "mailbox",
    ) -> list[DeliveryAck]:
        experience = self._experiences.get(experience_id)
        if experience is None:
            raise KeyError(f"SharedExperience {experience_id} not found")
        transport = self._resolve_transport(transport_mode)
        acks: list[DeliveryAck] = []
        for brain_id in target_brain_ids:
            peer = self._peers.get(brain_id)
            if peer is None or not peer.active:
                ack = self._record_ack(experience_id, brain_id, transport.mode, AckStatus.FAILED, "Target peer not active or not discovered")
                acks.append(ack)
                continue
            try:
                transport.deliver(peer, experience)
                ack = self._record_ack(experience_id, brain_id, transport.mode, AckStatus.DELIVERED, None)
            except Exception as exc:
                ack = self._record_ack(experience_id, brain_id, transport.mode, AckStatus.FAILED, str(exc))
            acks.append(ack)
        return acks

    def list_acks(self, message_id: str) -> list[DeliveryAck]:
        return [ack for ack in self._acks.values() if ack.message_id == message_id]

    def create_consensus_proposal(
        self,
        *,
        topic: str,
        payload: dict[str, Any],
        quorum: int,
        risk_level: str = "medium",
    ) -> ConsensusProposal:
        proposal = ConsensusProposal(
            proposer_brain_id=self.local_brain_id,
            topic=topic,
            payload=payload,
            quorum=quorum,
            risk_level=risk_level,  # type: ignore[arg-type]
        )
        self._proposals[proposal.proposal_id] = proposal
        self._votes[proposal.proposal_id] = {}
        return proposal

    def submit_vote(
        self,
        *,
        proposal_id: str,
        voter_brain_id: str,
        decision: VoteDecision,
        rationale: str,
    ) -> ConsensusProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"ConsensusProposal {proposal_id} not found")
        peer = self._peers.get(voter_brain_id)
        if peer is None or not peer.active:
            raise ValueError(f"Voter {voter_brain_id} is not an active discovered peer")
        vote_payload = {
            "proposal_id": proposal_id,
            "voter_brain_id": voter_brain_id,
            "decision": decision.value,
            "rationale": rationale,
        }
        vote = ConsensusVote(
            proposal_id=proposal_id,
            voter_brain_id=voter_brain_id,
            decision=decision,
            rationale=rationale,
            signature=self._sign(vote_payload, peer.shared_secret),
        )
        self._votes[proposal_id][voter_brain_id] = vote
        return self._evaluate_consensus(proposal_id)

    def get_consensus_proposal(self, proposal_id: str) -> ConsensusProposal | None:
        return self._proposals.get(proposal_id)

    def list_votes(self, proposal_id: str) -> list[ConsensusVote]:
        return list(self._votes.get(proposal_id, {}).values())

    def verify_shared_experience(self, experience: SharedExperience) -> bool:
        peer = self._peers.get(experience.source_brain_id)
        if peer is None:
            return False
        signed = experience.model_dump(mode="json", exclude={"signature", "accepted_to_core_memory", "quarantine_reason"})
        expected = self._sign(signed, peer.shared_secret)
        return hmac.compare_digest(experience.signature, expected)

    def _evaluate_consensus(self, proposal_id: str) -> ConsensusProposal:
        proposal = self._proposals[proposal_id]
        votes = self._votes.get(proposal_id, {})
        approvals = sum(1 for vote in votes.values() if vote.decision == VoteDecision.APPROVE)
        rejections = sum(1 for vote in votes.values() if vote.decision == VoteDecision.REJECT)
        status = proposal.status
        passed = proposal.passed
        if approvals >= proposal.quorum:
            status = ConsensusStatus.PASSED
            passed = True
        elif rejections >= proposal.quorum:
            status = ConsensusStatus.REJECTED
            passed = False
        updated = proposal.model_copy(
            update={
                "status": status,
                "passed": passed,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._proposals[proposal_id] = updated
        return updated

    def _record_ack(
        self,
        message_id: str,
        target_brain_id: str,
        transport_mode: str,
        status: AckStatus,
        error: str | None,
    ) -> DeliveryAck:
        ack = DeliveryAck(
            message_id=message_id,
            target_brain_id=target_brain_id,
            transport_mode=transport_mode,  # type: ignore[arg-type]
            status=status,
            attempts=1,
            error=error,
            delivered_at=datetime.now(timezone.utc) if status == AckStatus.DELIVERED else None,
            updated_at=datetime.now(timezone.utc),
        )
        self._acks[ack.ack_id] = ack
        return ack

    def _resolve_transport(self, transport_mode: str) -> ExperienceTransport:
        if transport_mode == "mailbox":
            return self.mailbox_transport
        if transport_mode == "http":
            return self.http_transport
        raise ValueError(f"Unsupported transport mode: {transport_mode}")

    def _sign(self, payload: dict[str, Any], secret: str) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"hmac-sha256={digest}"
