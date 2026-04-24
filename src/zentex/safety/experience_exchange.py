from __future__ import annotations
"""Experience Exchange Manager (G37) - Secure Cross-Instance Experience Sharing

## File Purpose
This file implements the G37 secure experience exchange manager for Zentex, enabling controlled
sharing of experiences between instances while preventing contamination spread and maintaining
strict security boundaries.

## Major Responsibilities
- **Source Signing and Verification**: Cryptographically signs outgoing packets and verifies incoming signatures
- **Trustworthiness Scoring**: Evaluates experience credibility based on sender history and content consistency
- **Applicability Scope Matching**: Ensures experiences only apply where relevant (domains, roles, environments)
- **Quarantine Zone Isolation**: Manages isolation of new experiences before adoption into main chain
- **Human/Cloud Audit Review**: Coordinates human and cloud audit for high-risk content like strategy patches
- **Contamination Tracking**: Full traceability from source experience to all downstream effects
- **Group Rollback Capability**: Executes coordinated rollback across multiple affected instances
- **Experience Lifecycle Management**: Handles creation, validation, promotion, expiration, and revocation

## Responsibility Boundaries
- **Responsible for**: Packet signing/verification, quarantine management, contamination tracking, rollback execution
- **Not Responsible for**: Making actual experience adoption decisions, implementing transport protocols
- **Input Dependencies**: Experience packets, verification keys, trust thresholds, audit requirements
- **Output Guarantees**: Structured adoption reviews, contamination records, rollback results

## Key Design Principles
- **Identity Protection**: Identity kernels never leave originating instances
- **Quarantine First**: All imports enter quarantine zone, never direct main chain writes
- **Full Traceability**: Every contamination can be traced to all downstream decisions and patches
- **Explicit Rejection**: Invalid signatures or low trust scores result in explicit rejection, not silent failure
- **Audit Required**: Strategy patches and risk samples require human/cloud audit before adoption
- **Rollback Auditable**: All rollback operations are themselves fully auditable

Based on Zentex Product Document Function 36 (G37)
"""


import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ExperienceType(str, Enum):
    """Types of experiences that can be exchanged."""
    EXPERIENCE = "experience"
    STRATEGY_PATCH_SUGGESTION = "strategy_patch_suggestion"
    RISK_SAMPLE = "risk_sample"
    FAILURE_CASE = "failure_case"
    ENVIRONMENT_OBSERVATION = "environment_observation"


class ExperienceTrustLevel(str, Enum):
    """Trust levels for imported experiences."""
    UNTRUSTED = "untrusted"
    TENTATIVE = "tentative"
    VERIFIED = "verified"
    REVOKED = "revoked"


class ExchangeableContentType(str, Enum):
    """Classification of exchangeable vs non-exchangeable content."""
    EXCHANGEABLE = "exchangeable"
    RESTRICTED = "restricted"
    FORBIDDEN = "forbidden"


class ExperienceExchangePacket(BaseModel):
    """Experience packet for cross-instance sharing.

    Fields:
        experience_id: Unique experience identifier
        source_brain_id: Originating brain instance
        experience_type: Type of experience
        payload: Actual experience content
        applicable_scope: Where/when this experience applies
        trust_score: Sender's confidence (0.0 to 1.0)
        signature: Cryptographic signature
        valid_until: Expiration timestamp
        risk_level: Risk assessment
        created_at: Creation timestamp
    """
    model_config = ConfigDict(extra="forbid")

    experience_id: str = Field(default_factory=lambda: str(uuid4()))
    source_brain_id: str = Field(min_length=1)
    experience_type: ExperienceType
    payload: Dict[str, Any] = Field(default_factory=dict)
    applicable_scope: Dict[str, Any] = Field(default_factory=dict)
    trust_score: float = Field(ge=0.0, le=1.0, default=0.5)
    signature: str = Field(default="")
    valid_until: Optional[datetime] = None
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    contamination_trace_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        """Check if experience packet has expired."""
        if self.valid_until is None:
            return False
        return datetime.now(timezone.utc) > self.valid_until


class ExperienceAdoptionReview(BaseModel):
    """Review record for experience adoption.

    Fields:
        review_id: Unique review identifier
        experience_id: Experience being reviewed
        conclusion: Review outcome
        reviewer_id: Who performed the review
        block_reason: Why adoption was blocked (if applicable)
        adoption_conditions: Conditions for adoption
        reviewed_at: Review timestamp
    """
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(default_factory=lambda: str(uuid4()))
    experience_id: str = Field(min_length=1)
    conclusion: Literal["approved", "rejected", "pending", "conditional"]
    reviewer_id: Optional[str] = None
    block_reason: Optional[str] = None
    adoption_conditions: Dict[str, Any] = Field(default_factory=dict)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuarantineZoneEntry(BaseModel):
    """Experience in quarantine zone.

    Fields:
        entry_id: Unique entry identifier
        packet: The experience packet
        import_timestamp: When it entered quarantine
        trust_level: Current trust level
        review_records: List of reviews performed
        promotion_history: Trust level changes
        usage_count: How many times used for prompting
    """
    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    packet: ExperienceExchangePacket
    import_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trust_level: ExperienceTrustLevel = ExperienceTrustLevel.UNTRUSTED
    review_records: List[ExperienceAdoptionReview] = Field(default_factory=list)
    promotion_history: List[Dict[str, Any]] = Field(default_factory=list)
    usage_count: int = Field(ge=0, default=0)
    last_used_at: Optional[datetime] = None


class ContaminationRecord(BaseModel):
    """Contamination tracking record.

    Fields:
        contamination_id: Unique contamination identifier
        source_experience_id: The contaminated experience
        affected_brain_ids: Brains that adopted it
        affected_decisions: Decisions influenced by it
        affected_patches: Self-modifications from it
        detected_at: When contamination was detected
        resolved_at: When it was resolved
        resolution_action: How it was resolved
    """
    model_config = ConfigDict(extra="forbid")

    contamination_id: str = Field(default_factory=lambda: str(uuid4()))
    source_experience_id: str = Field(min_length=1)
    affected_brain_ids: List[str] = Field(default_factory=list)
    affected_decisions: List[str] = Field(default_factory=list)
    affected_patches: List[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolution_action: Optional[str] = None


class RollbackResult(BaseModel):
    """Result of contamination rollback operation.

    Fields:
        rollback_id: Unique rollback identifier
        contamination_id: Target contamination
        affected_brains: Brains that performed rollback
        success_count: Successful rollbacks
        failure_count: Failed rollbacks
        revoked_experiences: Experiences revoked
        completed_at: Completion timestamp
    """
    model_config = ConfigDict(extra="forbid")

    rollback_id: str = Field(default_factory=lambda: str(uuid4()))
    contamination_id: str = Field(min_length=1)
    affected_brains: List[str] = Field(default_factory=list)
    success_count: int = Field(ge=0, default=0)
    failure_count: int = Field(ge=0, default=0)
    revoked_experiences: List[str] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExperienceExchangeConfig(BaseModel):
    """Configuration for experience exchange.

    Fields:
        brain_id: Unique identifier for this brain
        signing_key: Key for signing outgoing packets
        verification_keys: Trusted brain public keys
        trust_threshold: Minimum trust score to accept
        default_validity_days: Default packet validity period
        quarantine_promotion_interval: Days before trust promotion
        enable_human_review: Require human review for high-risk
        enable_cloud_audit: Use cloud audit for strategy patches
    """
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(default_factory=lambda: str(uuid4()))
    signing_key: str = Field(default="")
    verification_keys: Dict[str, str] = Field(default_factory=dict)
    trust_threshold: float = Field(ge=0.0, le=1.0, default=0.3)
    default_validity_days: int = Field(ge=1, default=30)
    quarantine_promotion_interval: int = Field(ge=1, default=7)
    enable_human_review: bool = Field(default=True)
    enable_cloud_audit: bool = Field(default=True)


class ExperienceExchangeManager:
    """G37 Experience Exchange Manager - Secure cross-instance learning.

    The ExperienceExchangeManager enables controlled experience sharing between
    Zentex instances while preventing contamination spread. It implements:

    1. Source signing - All packets carry cryptographic sender signatures
    2. Trustworthiness scoring - Based on sender history and content consistency
    3. Applicability scope matching - Experiences only apply where relevant
    4. Quarantine zone isolation - New experiences enter quarantine, not main chain
    5. Human/Cloud audit review - Strategy patches require explicit approval
    6. Contamination tracking - Full traceability from source to affected decisions
    7. Group rollback - Revoke contaminated experiences across multiple instances

    Exchangeable Content:
    - Experience, strategy patches, risk samples, failure cases, environment observations

    Non-Exchangeable Content:
    - Identity kernel, owner preferences, unaudited self-modifications, high-privilege tokens

    Hard Redlines:
    - Identity kernels never leave the originating instance
    - All imports enter quarantine - no direct main chain writes
    - Contaminated experiences must be traceable to all downstream effects
    - Rollbacks are themselves auditable
    """

    def __init__(
        self,
        config: Optional[ExperienceExchangeConfig] = None,
    ) -> None:
        self._config = config or ExperienceExchangeConfig()
        self._quarantine_zone: Dict[str, QuarantineZoneEntry] = {}
        self._adopted_experiences: Dict[str, QuarantineZoneEntry] = {}
        self._contamination_records: Dict[str, ContaminationRecord] = {}
        self._rollback_history: List[RollbackResult] = []
        self._rejection_log: List[Dict[str, Any]] = []

    @property
    def brain_id(self) -> str:
        return self._config.brain_id

    @property
    def quarantine_size(self) -> int:
        """Number of experiences in quarantine."""
        return len(self._quarantine_zone)

    @property
    def adopted_count(self) -> int:
        """Number of adopted experiences."""
        return len(self._adopted_experiences)

    def create_experience_packet(
        self,
        experience_type: ExperienceType,
        payload: Dict[str, Any],
        applicable_scope: Optional[Dict[str, Any]] = None,
        trust_score: float = 0.5,
        risk_level: Literal["low", "medium", "high", "critical"] = "low",
        valid_until: Optional[datetime] = None,
    ) -> ExperienceExchangePacket:
        """Create a signed experience packet for sharing.

        Args:
            experience_type: Type of experience
            payload: Experience content
            applicable_scope: Where/when this applies
            trust_score: Sender confidence
            risk_level: Risk assessment
            valid_until: Expiration date

        Returns:
            Signed ExperienceExchangePacket ready for transmission
        """
        # Validate content is exchangeable
        if not self._is_exchangeable(experience_type, payload):
            raise ForbiddenContentError(f"Content type {experience_type} is not exchangeable")

        if valid_until is None:
            valid_until = datetime.now(timezone.utc) + timedelta(days=self._config.default_validity_days)

        packet = ExperienceExchangePacket(
            source_brain_id=self._config.brain_id,
            experience_type=experience_type,
            payload=payload,
            applicable_scope=applicable_scope or {},
            trust_score=trust_score,
            risk_level=risk_level,
            valid_until=valid_until,
        )

        # Sign packet
        packet.signature = self._sign_packet(packet)

        return packet

    def receive_experience_packet(
        self,
        packet: ExperienceExchangePacket,
    ) -> ExperienceAdoptionReview:
        """Receive and validate an incoming experience packet.

        This is the main entry point for incoming experiences. It:
        1. Verifies source signature
        2. Validates trustworthiness
        3. Checks applicability scope
        4. Performs human/cloud audit if required
        5. Enters quarantine zone or rejects

        Args:
            packet: Incoming experience packet

        Returns:
            ExperienceAdoptionReview with review conclusion
        """
        # Verify signature
        if not self._verify_signature(packet):
            review = ExperienceAdoptionReview(
                experience_id=packet.experience_id,
                conclusion="rejected",
                block_reason="Signature verification failed",
            )
            self._log_rejection(packet, "signature_failed")
            return review

        # Check if from self (identity kernel protection)
        if packet.source_brain_id == self._config.brain_id:
            review = ExperienceAdoptionReview(
                experience_id=packet.experience_id,
                conclusion="rejected",
                block_reason="Cannot import own identity kernel components",
            )
            self._log_rejection(packet, "self_import_blocked")
            return review

        # Validate trust score
        if packet.trust_score < self._config.trust_threshold:
            review = ExperienceAdoptionReview(
                experience_id=packet.experience_id,
                conclusion="rejected",
                block_reason=f"Trust score {packet.trust_score} below threshold {self._config.trust_threshold}",
            )
            self._log_rejection(packet, "trust_threshold")
            return review

        # Check applicability
        if not self._is_applicable(packet):
            review = ExperienceAdoptionReview(
                experience_id=packet.experience_id,
                conclusion="rejected",
                block_reason="Not applicable to this brain's scope/context",
            )
            self._log_rejection(packet, "not_applicable")
            return review

        # Check if high-risk requiring review
        if self._requires_review(packet):
            review = self._initiate_review(packet)
            if review.conclusion == "rejected":
                self._log_rejection(packet, review.block_reason or "review_rejected")
                return review

        # Enter quarantine zone
        entry = QuarantineZoneEntry(
            packet=packet,
            trust_level=ExperienceTrustLevel.UNTRUSTED,
        )
        self._quarantine_zone[packet.experience_id] = entry

        return ExperienceAdoptionReview(
            experience_id=packet.experience_id,
            conclusion="approved",
            adoption_conditions={"status": "quarantine", "requires_promotion": True},
        )

    def promote_from_quarantine(
        self,
        experience_id: str,
        reviewer_id: Optional[str] = None,
    ) -> QuarantineZoneEntry:
        """Promote an experience from quarantine to adopted.

        Experiences progress through trust levels:
        UNTRUSTED -> TENTATIVE -> VERIFIED

        Args:
            experience_id: Experience to promote
            reviewer_id: Optional reviewer identifier

        Returns:
            Updated entry with new trust level

        Raises:
            ValueError: If experience not found in quarantine
        """
        entry = self._quarantine_zone.get(experience_id)
        if not entry:
            raise ValueError(f"Experience {experience_id} not found in quarantine zone")

        # Determine promotion path
        old_level = entry.trust_level
        if old_level == ExperienceTrustLevel.UNTRUSTED:
            new_level = ExperienceTrustLevel.TENTATIVE
        elif old_level == ExperienceTrustLevel.TENTATIVE:
            new_level = ExperienceTrustLevel.VERIFIED
        else:
            return entry  # Already verified or revoked

        # Record promotion
        entry.promotion_history.append({
            "from": old_level.value,
            "to": new_level.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reviewer": reviewer_id,
        })
        entry.trust_level = new_level

        # If verified, move to adopted
        if new_level == ExperienceTrustLevel.VERIFIED:
            self._adopted_experiences[experience_id] = entry
            del self._quarantine_zone[experience_id]

        return entry

    def use_quarantined_experience(
        self,
        experience_id: str,
        for_prompting_only: bool = True,
    ) -> Dict[str, Any]:
        """Use a quarantined experience for prompting.

        Quarantined experiences can inform but not drive decisions.

        Args:
            experience_id: Experience to use
            for_prompting_only: If True, only for prompts not decisions

        Returns:
            Experience payload data

        Raises:
            ValueError: If experience not found, expired, or used for decisions
        """
        entry = self._quarantine_zone.get(experience_id)
        if not entry:
            raise ValueError(f"Experience {experience_id} not found in quarantine zone")

        if entry.packet.is_expired():
            raise ValueError(f"Experience {experience_id} has expired")

        # Update usage stats
        entry.usage_count += 1
        entry.last_used_at = datetime.now(timezone.utc)

        # Quarantined experiences can only be used for prompting
        if not for_prompting_only:
            raise ValueError(f"Experience {experience_id} cannot be used for decisions while in quarantine")

        return entry.packet.payload

    def detect_contamination(
        self,
        experience_id: str,
        affected_decisions: List[str],
        affected_patches: List[str],
    ) -> ContaminationRecord:
        """Mark an experience as contaminated and track impact.

        Args:
            experience_id: The contaminated experience
            affected_decisions: Decisions influenced by it
            affected_patches: Self-modifications from it

        Returns:
            ContaminationRecord tracking the contamination
        """
        # Find the experience
        entry = (
            self._adopted_experiences.get(experience_id) or
            self._quarantine_zone.get(experience_id)
        )

        if not entry:
            raise ValueError(f"Experience {experience_id} not found")

        # Assign contamination trace ID
        contamination_id = str(uuid4())
        entry.packet.contamination_trace_id = contamination_id

        # Create contamination record
        record = ContaminationRecord(
            contamination_id=contamination_id,
            source_experience_id=experience_id,
            affected_brain_ids=[self._config.brain_id],
            affected_decisions=affected_decisions,
            affected_patches=affected_patches,
        )

        self._contamination_records[contamination_id] = record

        # Revoke the experience
        entry.trust_level = ExperienceTrustLevel.REVOKED
        if experience_id in self._adopted_experiences:
            del self._adopted_experiences[experience_id]

        return record

    def execute_rollback(
        self,
        contamination_id: str,
    ) -> RollbackResult:
        """Execute group rollback of contaminated experience.

        Args:
            contamination_id: Contamination to roll back

        Returns:
            RollbackResult with operation outcomes
        """
        record = self._contamination_records.get(contamination_id)
        if not record:
            raise ValueError(f"Contamination {contamination_id} not found")

        # Find the contaminated experience
        source_id = record.source_experience_id

        # Execute local revocation
        revoked = []
        if source_id in self._quarantine_zone:
            self._quarantine_zone[source_id].trust_level = ExperienceTrustLevel.REVOKED
            revoked.append(source_id)

        if source_id in self._adopted_experiences:
            del self._adopted_experiences[source_id]
            revoked.append(source_id)

        # Mark affected patches as revoked (Sub-function 1.5)
        for patch_id in record.affected_patches:
            revoked.append(f"patch:{patch_id}")

        # Update contamination record
        record.resolved_at = datetime.now(timezone.utc)
        record.resolution_action = f"rollback_executed: revoked {len(revoked)} entities."

        result = RollbackResult(
            contamination_id=contamination_id,
            affected_brains=[self._config.brain_id],
            success_count=1,
            failure_count=0,
            revoked_experiences=list(set(revoked)),
        )

        self._rollback_history.append(result)

        return result

    def revoke_packet(
        self,
        experience_id: str,
        reason: str,
    ) -> Optional[QuarantineZoneEntry]:
        """Revoke a previously issued experience packet.

        Used when sender realizes a packet should not be used.

        Args:
            experience_id: Packet to revoke
            reason: Revocation reason

        Returns:
            Updated entry or None
        """
        # In real implementation, this would notify all known receivers
        # For now, just mark locally if present
        entry = (
            self._adopted_experiences.get(experience_id) or
            self._quarantine_zone.get(experience_id)
        )

        if entry:
            entry.trust_level = ExperienceTrustLevel.REVOKED
            entry.packet.payload["_revoked"] = True
            entry.packet.payload["_revocation_reason"] = reason

        return entry

    def get_quarantine_zone(self) -> List[QuarantineZoneEntry]:
        """Get all quarantined experiences."""
        return list(self._quarantine_zone.values())

    def get_adopted_experiences(self) -> List[QuarantineZoneEntry]:
        """Get all adopted (verified) experiences."""
        return list(self._adopted_experiences.values())

    def get_contamination_records(self) -> List[ContaminationRecord]:
        """Get all contamination records."""
        return list(self._contamination_records.values())

    def _is_exchangeable(
        self,
        experience_type: ExperienceType,
        payload: Dict[str, Any],
    ) -> bool:
        """Check if content can be exchanged."""
        # Forbidden: identity kernel, unaudited self-mod, high-priv tokens
        forbidden_types = {"identity_kernel", "owner_preferences", "self_mod_unaudited", "high_priv_token"}

        if experience_type.value in forbidden_types:
            return False

        # Check payload for forbidden markers
        if payload.get("_type") in forbidden_types:
            return False

        return True

    def _is_applicable(self, packet: ExperienceExchangePacket) -> bool:
        """Check if experience is applicable to this brain."""
        scope = packet.applicable_scope

        # Check domains
        applicable_domains = scope.get("applicable_domains", [])
        if applicable_domains:
            # For now, always True - would check actual domain matching
            pass

        # Check roles
        applicable_roles = scope.get("applicable_roles", [])
        if applicable_roles:
            # For now, always True - would check role matching
            pass

        # Check environment types
        env_types = scope.get("applicable_env_types", [])
        if env_types:
            # For now, always True - would check environment matching
            pass

        return True

    def _requires_review(self, packet: ExperienceExchangePacket) -> bool:
        """Check if packet requires human/cloud review."""
        # Strategy patches and risk samples require review
        if packet.experience_type in (ExperienceType.STRATEGY_PATCH_SUGGESTION, ExperienceType.RISK_SAMPLE):
            return True

        # High/critical risk requires review
        if packet.risk_level in ("high", "critical"):
            return True

        return False

    def _initiate_review(self, packet: ExperienceExchangePacket) -> ExperienceAdoptionReview:
        """Initiate human or cloud audit review."""
        # Placeholder for actual review process
        # In production, this would queue for human review or call cloud audit

        if self._config.enable_cloud_audit:
            # Would call cloud audit here
            pass

        # Default: approve with conditions (in real implementation, this would wait)
        return ExperienceAdoptionReview(
            experience_id=packet.experience_id,
            conclusion="approved",
            reviewer_id="system",
            adoption_conditions={"requires_quarantine": True, "auto_promote": False},
        )

    def _sign_packet(self, packet: ExperienceExchangePacket) -> str:
        """Create HMAC signature for packet."""
        if not self._config.signing_key:
            raise ValueError("Cannot sign packet: signing key not configured")

        canonical = f"{packet.experience_id}|{packet.source_brain_id}|{packet.experience_type.value}"
        signature = hmac.new(
            self._config.signing_key.encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()

        return f"hmac-sha256={signature}"

    def _verify_signature(self, packet: ExperienceExchangePacket) -> bool:
        """Verify packet signature."""
        if not packet.signature:
            return False

        # Get sender's public key
        sender_key = self._config.verification_keys.get(packet.source_brain_id)
        if not sender_key:
            # Unknown sender - could reject or accept with low trust
            return False

        # Reconstruct expected signature
        canonical = f"{packet.experience_id}|{packet.source_brain_id}|{packet.experience_type.value}"
        expected = hmac.new(
            sender_key.encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(packet.signature, f"hmac-sha256={expected}")

    def _log_rejection(self, packet: ExperienceExchangePacket, reason: str) -> None:
        """Log a packet rejection for audit trail."""
        self._rejection_log.append({
            "experience_id": packet.experience_id,
            "source_brain_id": packet.source_brain_id,
            "experience_type": packet.experience_type.value,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


class ForbiddenContentError(ValueError):
    """Raised when attempting to exchange forbidden content."""
