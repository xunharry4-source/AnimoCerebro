from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class InteractionOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    FAILURE = "failure"
    BREACH = "breach"
    CHEATING = "cheating"


class ReputationLevel(str, Enum):
    NOVICE = "novice"
    EXPERIENCED = "experienced"
    TRUSTED = "trusted"
    EXPERT = "expert"


class InteractionHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str = Field(default_factory=lambda: f"interaction:{uuid4().hex}")
    task_id: str = Field(min_length=1)
    brain_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    outcome: InteractionOutcome
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    occurred_at: str = Field(default_factory=lambda: _now().isoformat())
    notes: str = ""


class SocialTrustScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_id: str
    domain: str
    score: float
    sample_count: int
    success_rate: float
    recency_weight: float
    severe_breach_count: int
    trust_band: Literal["blocked", "low", "medium", "high"]
    last_interaction_at: str | None = None


class BrainReputationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_id: str
    reputation_domains: dict[str, ReputationLevel]
    trust_scores: dict[str, float]
    sample_counts: dict[str, int]
    severe_breach_domains: list[str]
    profile_source: Literal["interaction_history"] = "interaction_history"
    updated_at: str


class SocialPresenceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(min_length=1)
    current_load_level: Literal["low", "medium", "high", "overloaded"] = "medium"
    available_domains: list[str] = Field(default_factory=list)
    cooperation_willingness: Literal["available", "limited", "unavailable"] = "available"
    specialization_tags: list[str] = Field(default_factory=list)
    last_active_at: str = Field(default_factory=lambda: _now().isoformat())
    ttl_seconds: int = Field(default=300, ge=1)
    version: int = Field(default=1, ge=1)


class CooperationWillingnessSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(min_length=1)
    unavailable_domains: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    valid_until: str
    risk_ceiling: Literal["low", "medium", "high", "critical"] = "critical"


class DomainMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_id: str
    domain: str
    expertise_level: ReputationLevel
    trust_score: float
    freshness_score: float
    stale: bool
    current_load_level: str
    cooperation_willingness: str
    source_version: int


class CollectiveDomainMapGossip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_brain_id: str = Field(min_length=1)
    gossip_version: int = Field(ge=1)
    entries: list[DomainMapEntry] = Field(default_factory=list)


class CollectiveDomainMapGossipResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_brain_id: str
    gossip_version: int
    accepted_count: int
    merged_domains: list[str]


class SocialRoutingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_domain: str = Field(min_length=1)
    required_expertise: ReputationLevel = ReputationLevel.NOVICE
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    urgency: Literal["low", "medium", "high", "critical"] = "medium"
    goal_security_review_passed: bool = False
    authorized_force_route: bool = False


class SocialRouteCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brain_id: str
    domain: str
    recommendation_score: float
    trust_score: float
    expertise_level: ReputationLevel
    freshness_score: float
    current_load_level: str
    accepted_by_willingness: bool
    reasons: list[str]


class SocialRoutingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: str
    task_domain: str
    recommendation_only: bool
    requires_final_decision: bool
    goal_security_review_passed: bool
    candidates: list[SocialRouteCandidate]
    rejected_candidates: list[SocialRouteCandidate]


class SocialAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_type: str
    brain_id: str | None = None
    domain: str | None = None
    payload: dict[str, Any]
    created_at: str


class SocialCommunicationRuntime:
    def __init__(self, *, min_presence_interval_seconds: int = 30) -> None:
        self.min_presence_interval_seconds = min_presence_interval_seconds
        self._interactions: list[InteractionHistoryRecord] = []
        self._presence: dict[str, SocialPresenceSignal] = {}
        self._willingness: dict[str, CooperationWillingnessSignal] = {}
        self._gossip_versions: dict[str, int] = {}
        self._gossip_domain_entries: dict[tuple[str, str, str], DomainMapEntry] = {}
        self._audit: list[SocialAuditEvent] = []

    def record_interaction(self, record: InteractionHistoryRecord) -> dict[str, Any]:
        self._interactions.append(record)
        score = self.trust_score(record.brain_id, record.domain)
        profile = self.reputation(record.brain_id)
        self._audit_event(
            "interaction_recorded",
            brain_id=record.brain_id,
            domain=record.domain,
            payload={
                "task_id": record.task_id,
                "outcome": record.outcome.value,
                "quality_score": record.quality_score,
                "trust_score": score.model_dump(mode="json"),
            },
        )
        return {
            "record": record.model_dump(mode="json"),
            "trust_score": score.model_dump(mode="json"),
            "reputation_profile": profile.model_dump(mode="json"),
        }

    def trust_score(self, brain_id: str, domain: str) -> SocialTrustScore:
        records = [item for item in self._interactions if item.brain_id == brain_id and item.domain == domain]
        if not records:
            return SocialTrustScore(
                brain_id=brain_id,
                domain=domain,
                score=0.0,
                sample_count=0,
                success_rate=0.0,
                recency_weight=0.0,
                severe_breach_count=0,
                trust_band="low",
            )
        now = _now()
        weights: list[float] = []
        weighted_scores: list[float] = []
        successes = 0
        severe = 0
        last_at: datetime | None = None
        for record in records:
            occurred = _parse_dt(record.occurred_at) or now
            last_at = max(last_at or occurred, occurred)
            age_days = max(0.0, (now - occurred).total_seconds() / 86_400.0)
            recency = max(0.2, 1.0 - min(age_days / 180.0, 0.8))
            base = self._outcome_score(record.outcome, record.quality_score)
            if record.outcome in {InteractionOutcome.SUCCESS, InteractionOutcome.PARTIAL}:
                successes += 1
            if record.outcome in {InteractionOutcome.BREACH, InteractionOutcome.CHEATING}:
                severe += 1
            weights.append(recency)
            weighted_scores.append(base * recency)
        raw_score = sum(weighted_scores) / max(sum(weights), 0.001)
        if severe:
            raw_score = max(0.0, raw_score - min(0.7, severe * 0.35))
        score = round(max(0.0, min(1.0, raw_score)), 6)
        success_rate = round(successes / len(records), 6)
        recency_weight = round(max(weights), 6)
        return SocialTrustScore(
            brain_id=brain_id,
            domain=domain,
            score=score,
            sample_count=len(records),
            success_rate=success_rate,
            recency_weight=recency_weight,
            severe_breach_count=severe,
            trust_band=self._trust_band(score, severe),
            last_interaction_at=last_at.isoformat() if last_at else None,
        )

    def reputation(self, brain_id: str) -> BrainReputationProfile:
        domains = sorted({item.domain for item in self._interactions if item.brain_id == brain_id})
        scores: dict[str, float] = {}
        counts: dict[str, int] = {}
        reputation: dict[str, ReputationLevel] = {}
        severe_domains: list[str] = []
        for domain in domains:
            score = self.trust_score(brain_id, domain)
            scores[domain] = score.score
            counts[domain] = score.sample_count
            reputation[domain] = self._reputation_level(score)
            if score.severe_breach_count:
                severe_domains.append(domain)
        return BrainReputationProfile(
            brain_id=brain_id,
            reputation_domains=reputation,
            trust_scores=scores,
            sample_counts=counts,
            severe_breach_domains=severe_domains,
            updated_at=_now().isoformat(),
        )

    def broadcast_presence(self, signal: SocialPresenceSignal) -> SocialPresenceSignal:
        existing = self._presence.get(signal.brain_id)
        signal_time = _parse_dt(signal.last_active_at) or _now()
        if existing:
            existing_time = _parse_dt(existing.last_active_at) or _now()
            delta = (signal_time - existing_time).total_seconds()
            if signal.version <= existing.version:
                raise ValueError("SocialPresenceSignal version must increase")
            if delta < self.min_presence_interval_seconds:
                raise ValueError("SocialPresenceSignal broadcast frequency limit exceeded")
        self._presence[signal.brain_id] = signal
        self._audit_event(
            "presence_broadcast",
            brain_id=signal.brain_id,
            payload=signal.model_dump(mode="json"),
        )
        return signal

    def get_presence(self, brain_id: str) -> dict[str, Any]:
        signal = self._presence.get(brain_id)
        if signal is None:
            raise KeyError(brain_id)
        return {
            **signal.model_dump(mode="json"),
            "stale": self._presence_stale(signal),
            "freshness_score": self._freshness_score(signal),
        }

    def publish_willingness(self, signal: CooperationWillingnessSignal) -> CooperationWillingnessSignal:
        valid_until = _parse_dt(signal.valid_until)
        if valid_until is None or valid_until <= _now():
            raise ValueError("CooperationWillingnessSignal valid_until must be in the future")
        self._willingness[signal.brain_id] = signal
        self._audit_event(
            "willingness_published",
            brain_id=signal.brain_id,
            payload=signal.model_dump(mode="json"),
        )
        return signal

    def domain_map(self, domain: str | None = None) -> dict[str, Any]:
        domains = [domain] if domain else sorted({item.domain for item in self._interactions})
        entries_by_key: dict[tuple[str, str], DomainMapEntry] = {}
        for candidate_domain in domains:
            brain_ids = sorted({item.brain_id for item in self._interactions if item.domain == candidate_domain})
            for brain_id in brain_ids:
                trust = self.trust_score(brain_id, candidate_domain)
                presence = self._presence.get(brain_id)
                entry = DomainMapEntry(
                    brain_id=brain_id,
                    domain=candidate_domain,
                    expertise_level=self._reputation_level(trust),
                    trust_score=trust.score,
                    freshness_score=self._freshness_score(presence),
                    stale=self._presence_stale(presence),
                    current_load_level=presence.current_load_level if presence else "unknown",
                    cooperation_willingness=presence.cooperation_willingness if presence else "unknown",
                    source_version=presence.version if presence else 0,
                )
                entries_by_key[(candidate_domain, brain_id)] = entry
        for entry in self._gossip_domain_entries.values():
            if domain and entry.domain != domain:
                continue
            key = (entry.domain, entry.brain_id)
            existing = entries_by_key.get(key)
            if existing is None or (entry.source_version, entry.trust_score) > (existing.source_version, existing.trust_score):
                entries_by_key[key] = entry
        entries = list(entries_by_key.values())
        entries.sort(key=lambda item: (item.domain, -item.trust_score, -item.freshness_score, item.brain_id))
        return {
            "items": [item.model_dump(mode="json") for item in entries],
            "count": len(entries),
        }

    def merge_domain_map_gossip(self, payload: CollectiveDomainMapGossip) -> CollectiveDomainMapGossipResult:
        current_version = self._gossip_versions.get(payload.source_brain_id, 0)
        if payload.gossip_version <= current_version:
            raise ValueError("CollectiveDomainMap gossip_version must increase")
        accepted = 0
        merged_domains: set[str] = set()
        for entry in payload.entries:
            if entry.stale:
                continue
            versioned = entry.model_copy(update={"source_version": payload.gossip_version})
            self._gossip_domain_entries[(payload.source_brain_id, entry.domain, entry.brain_id)] = versioned
            accepted += 1
            merged_domains.add(entry.domain)
        self._gossip_versions[payload.source_brain_id] = payload.gossip_version
        result = CollectiveDomainMapGossipResult(
            source_brain_id=payload.source_brain_id,
            gossip_version=payload.gossip_version,
            accepted_count=accepted,
            merged_domains=sorted(merged_domains),
        )
        self._audit_event(
            "domain_map_gossip_merged",
            brain_id=payload.source_brain_id,
            payload=result.model_dump(mode="json"),
        )
        return result

    def route(self, request: SocialRoutingRequest) -> SocialRoutingResult:
        if not request.goal_security_review_passed:
            raise ValueError("goal_security_review must pass before social routing recommendations")
        entries = [
            DomainMapEntry.model_validate(item)
            for item in self.domain_map(request.task_domain)["items"]
        ]
        candidates: list[SocialRouteCandidate] = []
        rejected: list[SocialRouteCandidate] = []
        for entry in entries:
            trust = self.trust_score(entry.brain_id, request.task_domain)
            willing, willingness_reason = self._willing_for(entry.brain_id, request.task_domain, request.risk_level)
            expertise_ok = self._expertise_rank(entry.expertise_level) >= self._expertise_rank(request.required_expertise)
            load_penalty = {"low": 0.0, "medium": 0.06, "high": 0.16, "overloaded": 0.35, "unknown": 0.12}.get(
                entry.current_load_level,
                0.12,
            )
            urgency_bonus = {"low": 0.0, "medium": 0.02, "high": 0.04, "critical": 0.06}[request.urgency]
            score = round(max(0.0, min(1.0, trust.score + entry.freshness_score * 0.12 + urgency_bonus - load_penalty)), 6)
            reasons = [
                f"trust_score={trust.score}",
                f"expertise={entry.expertise_level.value}",
                f"freshness_score={entry.freshness_score}",
                f"load={entry.current_load_level}",
                willingness_reason,
                "recommendation_only_final_decision_remains_with_requester",
            ]
            candidate = SocialRouteCandidate(
                brain_id=entry.brain_id,
                domain=request.task_domain,
                recommendation_score=score,
                trust_score=trust.score,
                expertise_level=entry.expertise_level,
                freshness_score=entry.freshness_score,
                current_load_level=entry.current_load_level,
                accepted_by_willingness=willing,
                reasons=reasons,
            )
            if willing and expertise_ok and trust.trust_band != "blocked":
                candidates.append(candidate)
            else:
                rejected.append(candidate)
        candidates.sort(key=lambda item: (-item.recommendation_score, item.brain_id))
        rejected.sort(key=lambda item: (-item.recommendation_score, item.brain_id))
        result = SocialRoutingResult(
            route_id=f"social-route:{uuid4().hex}",
            task_domain=request.task_domain,
            recommendation_only=not request.authorized_force_route,
            requires_final_decision=True,
            goal_security_review_passed=True,
            candidates=candidates,
            rejected_candidates=rejected,
        )
        self._audit_event(
            "social_route_recommended",
            domain=request.task_domain,
            payload=result.model_dump(mode="json"),
        )
        return result

    def list_interactions(self, brain_id: str | None = None, domain: str | None = None) -> list[InteractionHistoryRecord]:
        rows = self._interactions
        if brain_id:
            rows = [item for item in rows if item.brain_id == brain_id]
        if domain:
            rows = [item for item in rows if item.domain == domain]
        return list(rows)

    def list_audit(self) -> list[SocialAuditEvent]:
        return list(self._audit)

    def _willing_for(self, brain_id: str, domain: str, risk_level: str) -> tuple[bool, str]:
        signal = self._willingness.get(brain_id)
        if not signal:
            return True, "willingness=default_available"
        valid_until = _parse_dt(signal.valid_until)
        if valid_until is None or valid_until <= _now():
            return True, "willingness=expired"
        if domain in signal.unavailable_domains:
            return False, f"willingness=blocked:{signal.reason}"
        if self._risk_rank(risk_level) > self._risk_rank(signal.risk_ceiling):
            return False, f"willingness=risk_above_ceiling:{signal.risk_ceiling}"
        return True, "willingness=accepted"

    def _audit_event(self, event_type: str, *, payload: dict[str, Any], brain_id: str | None = None, domain: str | None = None) -> None:
        self._audit.append(
            SocialAuditEvent(
                event_id=f"social-audit:{uuid4().hex}",
                event_type=event_type,
                brain_id=brain_id,
                domain=domain,
                payload=payload,
                created_at=_now().isoformat(),
            )
        )

    @staticmethod
    def _outcome_score(outcome: InteractionOutcome, quality_score: float) -> float:
        base = {
            InteractionOutcome.SUCCESS: 0.78,
            InteractionOutcome.PARTIAL: 0.56,
            InteractionOutcome.TIMEOUT: 0.32,
            InteractionOutcome.FAILURE: 0.22,
            InteractionOutcome.BREACH: 0.04,
            InteractionOutcome.CHEATING: 0.0,
        }[outcome]
        return max(0.0, min(1.0, base * 0.7 + quality_score * 0.3))

    @staticmethod
    def _trust_band(score: float, severe: int) -> Literal["blocked", "low", "medium", "high"]:
        if severe:
            return "blocked"
        if score >= 0.72:
            return "high"
        if score >= 0.45:
            return "medium"
        return "low"

    @staticmethod
    def _reputation_level(score: SocialTrustScore) -> ReputationLevel:
        if score.sample_count >= 5 and score.score >= 0.82:
            return ReputationLevel.EXPERT
        if score.sample_count >= 3 and score.score >= 0.72:
            return ReputationLevel.TRUSTED
        if score.sample_count >= 2 and score.score >= 0.5:
            return ReputationLevel.EXPERIENCED
        return ReputationLevel.NOVICE

    @staticmethod
    def _expertise_rank(level: ReputationLevel) -> int:
        return {
            ReputationLevel.NOVICE: 0,
            ReputationLevel.EXPERIENCED: 1,
            ReputationLevel.TRUSTED: 2,
            ReputationLevel.EXPERT: 3,
        }[level]

    @staticmethod
    def _risk_rank(level: str) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[level]

    @staticmethod
    def _presence_stale(signal: SocialPresenceSignal | None) -> bool:
        if signal is None:
            return True
        active_at = _parse_dt(signal.last_active_at) or _now()
        return (_now() - active_at).total_seconds() > signal.ttl_seconds

    @staticmethod
    def _freshness_score(signal: SocialPresenceSignal | None) -> float:
        if signal is None:
            return 0.0
        active_at = _parse_dt(signal.last_active_at) or _now()
        age = max(0.0, (_now() - active_at).total_seconds())
        return round(max(0.0, min(1.0, 1.0 - (age / max(signal.ttl_seconds, 1)))), 6)


def build_default_social_communication_runtime() -> SocialCommunicationRuntime:
    return SocialCommunicationRuntime()
