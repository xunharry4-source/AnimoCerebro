"""G37 controlled cross-Zentex evolution and experience exchange."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


UTC = timezone.utc


class ExperienceType(str, Enum):
    EXPERIENCE = "experience"
    STRATEGY_PATCH_SUGGESTION = "strategy_patch_suggestion"
    RISK_SAMPLE = "risk_sample"
    FAILURE_CASE = "failure_case"
    ENVIRONMENT_OBSERVATION = "environment_observation"


class ExperienceTrustLevel(str, Enum):
    UNTRUSTED = "untrusted"
    TENTATIVE = "tentative"
    VERIFIED = "verified"
    REVOKED = "revoked"


class ExperienceReviewConclusion(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    CONDITIONAL = "conditional"


class ApplicableExperienceScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicable_domains: list[str] = Field(default_factory=list)
    applicable_roles: list[str] = Field(default_factory=list)
    applicable_risk_levels: list[str] = Field(default_factory=list)
    applicable_env_types: list[str] = Field(default_factory=list)


class ExperienceExchangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str
    signing_key: str = Field(min_length=8)
    verification_keys: dict[str, str] = Field(default_factory=dict)
    local_domains: list[str] = Field(default_factory=list)
    local_roles: list[str] = Field(default_factory=list)
    local_risk_levels: list[str] = Field(default_factory=lambda: ["low", "medium"])
    local_env_types: list[str] = Field(default_factory=list)
    trust_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    default_validity_days: int = Field(default=30, ge=1)


class ExperienceExchangePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experience_id: str = Field(default_factory=lambda: f"g37-exp-{uuid4().hex[:12]}")
    source_brain_id: str
    experience_type: ExperienceType
    payload: dict[str, Any] = Field(default_factory=dict)
    applicable_scope: ApplicableExperienceScope = Field(default_factory=ApplicableExperienceScope)
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    signature: str = ""
    valid_until: datetime
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    contamination_trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperienceAdoptionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(default_factory=lambda: f"g37-review-{uuid4().hex[:12]}")
    experience_id: str
    conclusion: ExperienceReviewConclusion
    reviewer_id: str | None = None
    block_reason: str | None = None
    adoption_conditions: dict[str, Any] = Field(default_factory=dict)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperienceQuarantineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(default_factory=lambda: f"g37-quarantine-{uuid4().hex[:12]}")
    packet: ExperienceExchangePacket
    import_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trust_level: ExperienceTrustLevel = ExperienceTrustLevel.UNTRUSTED
    review_required: bool = False
    review_records: list[ExperienceAdoptionReview] = Field(default_factory=list)
    promotion_history: list[dict[str, Any]] = Field(default_factory=list)
    usage_count: int = 0
    last_used_at: datetime | None = None
    can_drive_decisions: bool = False


class ExperienceContaminationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contamination_id: str = Field(default_factory=lambda: f"g37-contamination-{uuid4().hex[:12]}")
    source_experience_id: str
    affected_brain_ids: list[str] = Field(default_factory=list)
    affected_decisions: list[str] = Field(default_factory=list)
    affected_patches: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolution_action: str | None = None


class ExperienceRollbackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rollback_id: str = Field(default_factory=lambda: f"g37-rollback-{uuid4().hex[:12]}")
    contamination_id: str
    affected_brains: list[str]
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    revoked_experiences: list[str]
    rollback_scope: Literal["partial", "full"] = "full"
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperienceRevocationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revocation_id: str = Field(default_factory=lambda: f"g37-revoke-{uuid4().hex[:12]}")
    experience_id: str
    source_brain_id: str
    reason: str
    revoked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperienceAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(default_factory=lambda: f"g37-audit-{uuid4().hex[:12]}")
    action: str
    experience_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperienceExchange:
    """Fail-closed G37 exchange manager with quarantine-first adoption."""

    FORBIDDEN_PAYLOAD_TYPES = {
        "identity_kernel",
        "owner_preference_hard_write",
        "owner_preferences",
        "unaudited_self_rewrite",
        "self_mod_unaudited",
        "high_privilege_token",
        "high_priv_token",
    }

    def __init__(self, config: ExperienceExchangeConfig) -> None:
        self.config = config
        self._quarantine: dict[str, ExperienceQuarantineEntry] = {}
        self._adopted: dict[str, ExperienceQuarantineEntry] = {}
        self._reviews: dict[str, list[ExperienceAdoptionReview]] = {}
        self._contamination: dict[str, ExperienceContaminationRecord] = {}
        self._rollbacks: list[ExperienceRollbackResult] = []
        self._revocations: dict[str, ExperienceRevocationRecord] = {}
        self._rejections: list[ExperienceAdoptionReview] = []
        self._decision_links: dict[str, dict[str, set[str]]] = {}
        self._audits: list[ExperienceAuditEvent] = []

    def create_packet(
        self,
        *,
        experience_type: ExperienceType,
        payload: dict[str, Any],
        applicable_scope: ApplicableExperienceScope | None = None,
        trust_score: float = 0.5,
        risk_level: Literal["low", "medium", "high", "critical"] = "low",
        valid_until: datetime | None = None,
    ) -> ExperienceExchangePacket:
        self._validate_exchangeable(experience_type, payload)
        packet = ExperienceExchangePacket(
            source_brain_id=self.config.brain_id,
            experience_type=experience_type,
            payload=payload,
            applicable_scope=applicable_scope or ApplicableExperienceScope(),
            trust_score=trust_score,
            risk_level=risk_level,
            valid_until=valid_until or datetime.now(UTC) + timedelta(days=self.config.default_validity_days),
        )
        signed = packet.model_copy(update={"signature": self._sign(packet)})
        self._audit("packet_created", signed.experience_id, signed.model_dump(mode="json", exclude={"signature"}))
        return signed

    def receive_packet(self, packet: ExperienceExchangePacket) -> ExperienceAdoptionReview:
        rejection_reason = self._rejection_reason(packet)
        if rejection_reason:
            review = ExperienceAdoptionReview(
                experience_id=packet.experience_id,
                conclusion=ExperienceReviewConclusion.REJECTED,
                block_reason=rejection_reason,
            )
            self._rejections.append(review)
            self._audit("packet_rejected", packet.experience_id, review.model_dump(mode="json"))
            return review
        review_required = self._requires_review(packet)
        review = ExperienceAdoptionReview(
            experience_id=packet.experience_id,
            conclusion=ExperienceReviewConclusion.PENDING if review_required else ExperienceReviewConclusion.APPROVED,
            reviewer_id=None if review_required else "automatic_scope_signature_trust_gate",
            adoption_conditions={
                "status": "quarantine",
                "direct_main_chain_write": False,
                "requires_explicit_review": review_required,
            },
        )
        entry = ExperienceQuarantineEntry(
            packet=packet,
            review_required=review_required,
            review_records=[review],
            can_drive_decisions=False,
        )
        self._quarantine[packet.experience_id] = entry
        self._reviews.setdefault(packet.experience_id, []).append(review)
        self._audit("packet_quarantined", packet.experience_id, entry.model_dump(mode="json"))
        return review

    def submit_review(self, review: ExperienceAdoptionReview) -> ExperienceAdoptionReview:
        entry = self._quarantine.get(review.experience_id) or self._adopted.get(review.experience_id)
        if entry is None:
            raise KeyError(f"Unknown experience_id: {review.experience_id}")
        entry.review_records.append(review)
        self._reviews.setdefault(review.experience_id, []).append(review)
        if review.conclusion == ExperienceReviewConclusion.REJECTED:
            revoked = entry.model_copy(update={"trust_level": ExperienceTrustLevel.REVOKED, "can_drive_decisions": False})
            self._quarantine[review.experience_id] = revoked
        self._audit("adoption_review_recorded", review.experience_id, review.model_dump(mode="json"))
        return review

    def promote(self, experience_id: str, *, reviewer_id: str) -> ExperienceQuarantineEntry:
        entry = self._quarantine.get(experience_id)
        if entry is None:
            raise KeyError(f"Experience {experience_id} not found in quarantine")
        if entry.packet.valid_until <= datetime.now(UTC):
            downgraded = entry.model_copy(update={"trust_level": ExperienceTrustLevel.REVOKED, "can_drive_decisions": False})
            self._quarantine[experience_id] = downgraded
            raise ValueError("experience packet expired; revalidation required")
        if experience_id in self._revocations:
            raise ValueError("experience packet has been revoked")
        if entry.review_required and not self._has_approved_review(entry):
            raise ValueError("explicit human/cloud audit review is required before promotion")
        if any(review.conclusion == ExperienceReviewConclusion.REJECTED for review in entry.review_records):
            raise ValueError("rejected experience cannot be promoted")
        next_level = ExperienceTrustLevel.TENTATIVE if entry.trust_level == ExperienceTrustLevel.UNTRUSTED else ExperienceTrustLevel.VERIFIED
        history = [
            *entry.promotion_history,
            {
                "from": entry.trust_level.value,
                "to": next_level.value,
                "reviewer_id": reviewer_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ]
        updated = entry.model_copy(
            update={
                "trust_level": next_level,
                "promotion_history": history,
                "can_drive_decisions": next_level == ExperienceTrustLevel.VERIFIED,
            }
        )
        if next_level == ExperienceTrustLevel.VERIFIED:
            self._adopted[experience_id] = updated
            del self._quarantine[experience_id]
        else:
            self._quarantine[experience_id] = updated
        self._audit("experience_promoted", experience_id, updated.model_dump(mode="json"))
        return updated

    def use_quarantined_experience(self, experience_id: str, *, for_prompting_only: bool = True) -> dict[str, Any]:
        entry = self._quarantine.get(experience_id)
        if entry is None:
            raise KeyError(f"Experience {experience_id} not found in quarantine")
        if not for_prompting_only:
            raise ValueError("quarantined experience cannot drive decisions")
        if entry.packet.valid_until <= datetime.now(UTC):
            raise ValueError("experience packet expired; revalidation required")
        updated = entry.model_copy(update={"usage_count": entry.usage_count + 1, "last_used_at": datetime.now(UTC)})
        self._quarantine[experience_id] = updated
        self._audit("quarantined_experience_used_for_prompt", experience_id, {"usage_count": updated.usage_count})
        return updated.packet.payload

    def record_decision_influence(
        self,
        *,
        experience_id: str,
        affected_brain_id: str,
        decision_id: str,
        patch_id: str | None = None,
    ) -> dict[str, list[str]]:
        if experience_id not in self._adopted:
            raise ValueError("only verified adopted experiences can influence decisions")
        links = self._decision_links.setdefault(
            experience_id,
            {"affected_brain_ids": set(), "affected_decisions": set(), "affected_patches": set()},
        )
        links["affected_brain_ids"].add(affected_brain_id)
        links["affected_decisions"].add(decision_id)
        if patch_id:
            links["affected_patches"].add(patch_id)
        result = {key: sorted(value) for key, value in links.items()}
        self._audit("decision_influence_recorded", experience_id, result)
        return result

    def mark_contamination(
        self,
        *,
        experience_id: str,
        affected_brain_ids: list[str] | None = None,
        affected_decisions: list[str] | None = None,
        affected_patches: list[str] | None = None,
    ) -> ExperienceContaminationRecord:
        entry = self._adopted.get(experience_id) or self._quarantine.get(experience_id)
        if entry is None:
            raise KeyError(f"Unknown experience_id: {experience_id}")
        linked = self._decision_links.get(experience_id, {})
        contamination_id = f"g37-contamination-{uuid4().hex[:12]}"
        record = ExperienceContaminationRecord(
            contamination_id=contamination_id,
            source_experience_id=experience_id,
            affected_brain_ids=sorted(set(affected_brain_ids or []) | set(linked.get("affected_brain_ids", set())) | {self.config.brain_id}),
            affected_decisions=sorted(set(affected_decisions or []) | set(linked.get("affected_decisions", set()))),
            affected_patches=sorted(set(affected_patches or []) | set(linked.get("affected_patches", set()))),
        )
        updated_packet = entry.packet.model_copy(update={"contamination_trace_id": contamination_id})
        updated_entry = entry.model_copy(update={"packet": updated_packet, "trust_level": ExperienceTrustLevel.REVOKED, "can_drive_decisions": False})
        if experience_id in self._adopted:
            del self._adopted[experience_id]
        self._quarantine[experience_id] = updated_entry
        self._contamination[contamination_id] = record
        self._audit("contamination_marked", experience_id, record.model_dump(mode="json"))
        return record

    def execute_rollback(
        self,
        contamination_id: str,
        *,
        rollback_scope: Literal["partial", "full"] = "full",
    ) -> ExperienceRollbackResult:
        record = self._contamination.get(contamination_id)
        if record is None:
            raise KeyError(f"Unknown contamination_id: {contamination_id}")
        source_id = record.source_experience_id
        revoked = [source_id]
        entry = self._quarantine.get(source_id) or self._adopted.get(source_id)
        if entry:
            revoked_entry = entry.model_copy(update={"trust_level": ExperienceTrustLevel.REVOKED, "can_drive_decisions": False})
            self._quarantine[source_id] = revoked_entry
            self._adopted.pop(source_id, None)
        if rollback_scope == "full":
            revoked.extend([f"decision:{decision}" for decision in record.affected_decisions])
            revoked.extend([f"patch:{patch}" for patch in record.affected_patches])
        result = ExperienceRollbackResult(
            contamination_id=contamination_id,
            affected_brains=record.affected_brain_ids,
            success_count=len(record.affected_brain_ids),
            failure_count=0,
            revoked_experiences=sorted(set(revoked)),
            rollback_scope=rollback_scope,
        )
        record.resolved_at = result.completed_at
        record.resolution_action = f"{rollback_scope}_rollback_completed"
        self._rollbacks.append(result)
        self._audit("contamination_rollback_executed", source_id, result.model_dump(mode="json"))
        return result

    def revoke_packet(self, *, experience_id: str, source_brain_id: str, reason: str) -> ExperienceRevocationRecord:
        if source_brain_id != self.config.brain_id and source_brain_id not in self.config.verification_keys:
            raise ValueError("revocation source is not trusted")
        record = ExperienceRevocationRecord(experience_id=experience_id, source_brain_id=source_brain_id, reason=reason)
        self._revocations[experience_id] = record
        entry = self._quarantine.get(experience_id) or self._adopted.get(experience_id)
        if entry:
            updated = entry.model_copy(update={"trust_level": ExperienceTrustLevel.REVOKED, "can_drive_decisions": False})
            self._quarantine[experience_id] = updated
            self._adopted.pop(experience_id, None)
        self._audit("experience_revoked", experience_id, record.model_dump(mode="json"))
        return record

    def list_quarantine(self) -> list[ExperienceQuarantineEntry]:
        return list(self._quarantine.values())

    def list_adopted(self) -> list[ExperienceQuarantineEntry]:
        return list(self._adopted.values())

    def list_reviews(self, experience_id: str | None = None) -> list[ExperienceAdoptionReview]:
        if experience_id:
            return list(self._reviews.get(experience_id, []))
        return [review for reviews in self._reviews.values() for review in reviews]

    def list_contamination(self) -> list[ExperienceContaminationRecord]:
        return list(self._contamination.values())

    def list_rollbacks(self) -> list[ExperienceRollbackResult]:
        return list(self._rollbacks)

    def list_revocations(self) -> list[ExperienceRevocationRecord]:
        return list(self._revocations.values())

    def list_rejections(self) -> list[ExperienceAdoptionReview]:
        return list(self._rejections)

    def list_audit_events(self) -> list[ExperienceAuditEvent]:
        return list(self._audits)

    def _rejection_reason(self, packet: ExperienceExchangePacket) -> str | None:
        if not self._verify_signature(packet):
            return "signature verification failed"
        if packet.valid_until <= datetime.now(UTC):
            return "experience packet expired"
        if packet.trust_score < self.config.trust_threshold:
            return f"trust score {packet.trust_score} below threshold {self.config.trust_threshold}"
        if packet.source_brain_id == self.config.brain_id:
            return "self import is not allowed"
        try:
            self._validate_exchangeable(packet.experience_type, packet.payload)
        except ValueError as exc:
            return str(exc)
        if not self._is_applicable(packet):
            return "not applicable to receiver scope"
        if packet.experience_id in self._revocations:
            return "experience packet has been revoked"
        return None

    def _validate_exchangeable(self, experience_type: ExperienceType, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, sort_keys=True, default=str).lower()
        markers = set()
        if "_type" in payload:
            markers.add(str(payload["_type"]).lower())
        if "content_type" in payload:
            markers.add(str(payload["content_type"]).lower())
        if experience_type.value in self.FORBIDDEN_PAYLOAD_TYPES or markers.intersection(self.FORBIDDEN_PAYLOAD_TYPES):
            raise ValueError("forbidden content cannot be exchanged")
        forbidden_needles = ["identity_kernel", "owner preference", "高权限", "api_key", "secret_token", "private_key"]
        if any(needle in raw for needle in forbidden_needles):
            raise ValueError("payload contains forbidden identity/preference/token material")

    def _is_applicable(self, packet: ExperienceExchangePacket) -> bool:
        scope = packet.applicable_scope
        return (
            self._scope_matches(scope.applicable_domains, self.config.local_domains)
            and self._scope_matches(scope.applicable_roles, self.config.local_roles)
            and self._scope_matches(scope.applicable_risk_levels, self.config.local_risk_levels)
            and self._scope_matches(scope.applicable_env_types, self.config.local_env_types)
        )

    @staticmethod
    def _scope_matches(required: list[str], local: list[str]) -> bool:
        return not required or bool(set(required).intersection(local))

    @staticmethod
    def _requires_review(packet: ExperienceExchangePacket) -> bool:
        return packet.experience_type in {
            ExperienceType.STRATEGY_PATCH_SUGGESTION,
            ExperienceType.RISK_SAMPLE,
        } or packet.risk_level in {"high", "critical"}

    @staticmethod
    def _has_approved_review(entry: ExperienceQuarantineEntry) -> bool:
        return any(review.conclusion == ExperienceReviewConclusion.APPROVED and review.reviewer_id for review in entry.review_records)

    def _sign(self, packet: ExperienceExchangePacket) -> str:
        canonical = self._canonical_packet(packet)
        digest = hmac.new(self.config.signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"hmac-sha256={digest}"

    def _verify_signature(self, packet: ExperienceExchangePacket) -> bool:
        key = self.config.verification_keys.get(packet.source_brain_id)
        if not key or not packet.signature:
            return False
        canonical = self._canonical_packet(packet)
        digest = hmac.new(key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(packet.signature, f"hmac-sha256={digest}")

    @staticmethod
    def _canonical_packet(packet: ExperienceExchangePacket) -> str:
        payload = packet.model_dump(mode="json", exclude={"signature", "contamination_trace_id"})
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    def _audit(self, action: str, experience_id: str | None, detail: dict[str, Any]) -> None:
        self._audits.append(ExperienceAuditEvent(action=action, experience_id=experience_id, detail=detail))
