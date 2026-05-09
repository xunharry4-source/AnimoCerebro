from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    USER = "user"
    AGENT = "agent"
    ZENTEX = "zentex"
    UNKNOWN = "unknown"


class SignalType(str, Enum):
    STATEMENT = "statement"
    CAPABILITY_REPORT = "capability_report"
    BEHAVIOR = "behavior"
    INTENT_SIGNAL = "intent_signal"
    CONFIRMATION = "confirmation"
    CORRECTION = "correction"
    KNOWLEDGE_GAP = "knowledge_gap"
    HIGH_RISK_SIGNAL = "high_risk_signal"


class IntentStatus(str, Enum):
    HYPOTHESIS = "hypothesis"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class InteractionSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_id: str = Field(min_length=1)
    signal_type: SignalType
    content: str = Field(min_length=1)
    topics: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    risk_markers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeBoundaryEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    known_topics: list[str] = Field(default_factory=list)
    uncertain_topics: list[str] = Field(default_factory=list)
    likely_missing_topics: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class IntentHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(default_factory=lambda: str(uuid4()))
    content: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    status: IntentStatus = IntentStatus.HYPOTHESIS
    source_evidence_refs: list[str] = Field(default_factory=list)
    high_risk: bool = False
    requires_environment_confirmation: bool = True
    allowed_to_drive_high_risk_action: bool = False


class CommunicationStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation_granularity: Literal["brief", "balanced", "step_by_step", "expert"]
    collaboration_mode: Literal["confirm_first", "delegate_with_constraints", "direct_collaboration", "teach_and_confirm"]
    requires_confirmation_before_high_risk: bool = True
    rationale: str = Field(min_length=1)


class CorrectionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correction_id: str = Field(default_factory=lambda: str(uuid4()))
    rejected_hypothesis_id: str = Field(min_length=1)
    corrected_intent: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    confirmed: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MindModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    entity_type: EntityType
    knowledge_depth: Literal["unknown", "novice", "working", "expert"] = "unknown"
    tolerance_for_detail: Literal["low", "medium", "high"] = "medium"
    current_interaction_state: Literal["probing", "confirming", "collaborating", "blocked"] = "probing"
    trust_estimate: float = Field(default=0.5, ge=0.0, le=1.0)
    knowledge_boundary: KnowledgeBoundaryEstimate
    active_hypotheses: list[IntentHypothesis] = Field(default_factory=list)
    confirmed_intents: list[IntentHypothesis] = Field(default_factory=list)
    correction_history: list[CorrectionRecord] = Field(default_factory=list)
    recommended_strategy: CommunicationStrategy
    source_signal_ids: list[str] = Field(default_factory=list)
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revision: int = Field(default=1, ge=1)


class TheoryOfMindEngine:
    def __init__(self) -> None:
        self._models: dict[str, MindModel] = {}

    def observe_entity(
        self,
        *,
        entity_id: str,
        entity_type: EntityType,
        signals: list[InteractionSignal],
    ) -> MindModel:
        if not signals:
            raise ValueError("At least one interaction signal is required")
        invalid = [signal.signal_id for signal in signals if signal.entity_id != entity_id]
        if invalid:
            raise ValueError(f"Signals do not belong to entity {entity_id}: {invalid}")

        previous = self._models.get(entity_id)
        known_topics = set(previous.knowledge_boundary.known_topics if previous else [])
        uncertain_topics = set(previous.knowledge_boundary.uncertain_topics if previous else [])
        missing_topics = set(previous.knowledge_boundary.likely_missing_topics if previous else [])
        active = list(previous.active_hypotheses if previous else [])
        confirmed = list(previous.confirmed_intents if previous else [])
        corrections = list(previous.correction_history if previous else [])
        source_signal_ids = set(previous.source_signal_ids if previous else [])

        knowledge_depth_votes: list[str] = []
        detail_votes: list[str] = []
        trust_delta = 0.0

        for signal in signals:
            source_signal_ids.add(signal.signal_id)
            self._collect_topics(signal, known_topics, uncertain_topics, missing_topics)
            knowledge_depth = signal.metadata.get("knowledge_depth")
            if knowledge_depth in {"novice", "working", "expert"}:
                knowledge_depth_votes.append(str(knowledge_depth))
            tolerance = signal.metadata.get("tolerance_for_detail")
            if tolerance in {"low", "medium", "high"}:
                detail_votes.append(str(tolerance))
            trust_delta += self._trust_delta(signal)

            intent = self._extract_intent(signal)
            if intent is not None:
                hypothesis = self._build_hypothesis(signal, intent)
                if hypothesis.status == IntentStatus.CONFIRMED:
                    confirmed = self._replace_intent(confirmed, hypothesis)
                else:
                    active.append(hypothesis)

        knowledge_depth = self._choose_latest_vote(
            knowledge_depth_votes,
            previous.knowledge_depth if previous else "unknown",
        )
        tolerance_for_detail = self._choose_latest_vote(
            detail_votes,
            previous.tolerance_for_detail if previous else "medium",
        )
        boundary = KnowledgeBoundaryEstimate(
            known_topics=sorted(known_topics),
            uncertain_topics=sorted(topic for topic in uncertain_topics if topic not in known_topics),
            likely_missing_topics=sorted(topic for topic in missing_topics if topic not in known_topics),
            confidence=self._boundary_confidence(known_topics, uncertain_topics, missing_topics, signals),
        )
        trust_estimate = self._bounded((previous.trust_estimate if previous else 0.5) + trust_delta)
        active = [item for item in active if item.status == IntentStatus.HYPOTHESIS]
        interaction_state = self._interaction_state(active, confirmed)
        strategy = self._strategy(
            entity_type=entity_type,
            knowledge_depth=knowledge_depth,
            tolerance_for_detail=tolerance_for_detail,
            active_hypotheses=active,
            confirmed_intents=confirmed,
            missing_topics=boundary.likely_missing_topics,
        )
        model = MindModel(
            entity_id=entity_id,
            entity_type=entity_type,
            knowledge_depth=knowledge_depth,
            tolerance_for_detail=tolerance_for_detail,
            current_interaction_state=interaction_state,
            trust_estimate=trust_estimate,
            knowledge_boundary=boundary,
            active_hypotheses=active,
            confirmed_intents=confirmed,
            correction_history=corrections,
            recommended_strategy=strategy,
            source_signal_ids=sorted(source_signal_ids),
            revision=(previous.revision + 1 if previous else 1),
        )
        self._models[entity_id] = model
        return model

    def record_correction(
        self,
        *,
        entity_id: str,
        hypothesis_id: str,
        corrected_intent: str,
        evidence_ref: str,
        confirmed: bool = True,
    ) -> MindModel:
        model = self.get_mind_model(entity_id)
        if model is None:
            raise KeyError(f"MindModel {entity_id} not found")
        matched: IntentHypothesis | None = None
        remaining: list[IntentHypothesis] = []
        for hypothesis in model.active_hypotheses:
            if hypothesis.hypothesis_id == hypothesis_id:
                matched = hypothesis.model_copy(update={"status": IntentStatus.REJECTED})
            else:
                remaining.append(hypothesis)
        if matched is None:
            raise KeyError(f"IntentHypothesis {hypothesis_id} not found")

        correction = CorrectionRecord(
            rejected_hypothesis_id=hypothesis_id,
            corrected_intent=corrected_intent,
            evidence_ref=evidence_ref,
            confirmed=confirmed,
        )
        corrected = IntentHypothesis(
            content=corrected_intent,
            confidence=0.95 if confirmed else 0.7,
            status=IntentStatus.CONFIRMED if confirmed else IntentStatus.HYPOTHESIS,
            source_evidence_refs=[evidence_ref],
            high_risk=False,
            requires_environment_confirmation=not confirmed,
            allowed_to_drive_high_risk_action=False,
        )
        confirmed_intents = list(model.confirmed_intents)
        active = remaining
        if confirmed:
            confirmed_intents = self._replace_intent(confirmed_intents, corrected)
        else:
            active.append(corrected)

        revised = model.model_copy(
            update={
                "active_hypotheses": active,
                "confirmed_intents": confirmed_intents,
                "correction_history": [*model.correction_history, correction],
                "current_interaction_state": "confirming" if active else "collaborating",
                "recommended_strategy": self._strategy(
                    entity_type=model.entity_type,
                    knowledge_depth=model.knowledge_depth,
                    tolerance_for_detail=model.tolerance_for_detail,
                    active_hypotheses=active,
                    confirmed_intents=confirmed_intents,
                    missing_topics=model.knowledge_boundary.likely_missing_topics,
                ),
                "last_updated_at": datetime.now(timezone.utc),
                "revision": model.revision + 1,
            }
        )
        self._models[entity_id] = revised
        return revised

    def get_mind_model(self, entity_id: str) -> MindModel | None:
        return self._models.get(entity_id)

    def list_models(self) -> list[MindModel]:
        return sorted(self._models.values(), key=lambda item: item.entity_id)

    def _collect_topics(
        self,
        signal: InteractionSignal,
        known_topics: set[str],
        uncertain_topics: set[str],
        missing_topics: set[str],
    ) -> None:
        known_topics.update(str(topic) for topic in signal.metadata.get("known_topics", []) if str(topic).strip())
        uncertain_topics.update(str(topic) for topic in signal.metadata.get("uncertain_topics", []) if str(topic).strip())
        missing_topics.update(str(topic) for topic in signal.metadata.get("missing_topics", []) if str(topic).strip())
        if signal.signal_type in {SignalType.STATEMENT, SignalType.CAPABILITY_REPORT, SignalType.CONFIRMATION}:
            known_topics.update(signal.topics)
        elif signal.signal_type == SignalType.KNOWLEDGE_GAP:
            missing_topics.update(signal.topics)
        elif signal.signal_type in {SignalType.BEHAVIOR, SignalType.INTENT_SIGNAL}:
            uncertain_topics.update(signal.topics)

    def _extract_intent(self, signal: InteractionSignal) -> str | None:
        intent = signal.metadata.get("intent") or signal.metadata.get("confirmed_intent")
        if intent is not None and str(intent).strip():
            return str(intent).strip()
        if signal.signal_type in {SignalType.INTENT_SIGNAL, SignalType.HIGH_RISK_SIGNAL, SignalType.CONFIRMATION}:
            return signal.content.strip()
        return None

    def _build_hypothesis(self, signal: InteractionSignal, intent: str) -> IntentHypothesis:
        confirmed = signal.signal_type == SignalType.CONFIRMATION or signal.metadata.get("confirmed") is True
        high_risk = signal.signal_type == SignalType.HIGH_RISK_SIGNAL or bool(signal.risk_markers)
        source_refs = list(signal.evidence_refs) or [signal.signal_id]
        return IntentHypothesis(
            content=intent,
            confidence=float(signal.metadata.get("confidence", 0.9 if confirmed else 0.65)),
            status=IntentStatus.CONFIRMED if confirmed else IntentStatus.HYPOTHESIS,
            source_evidence_refs=source_refs,
            high_risk=high_risk,
            requires_environment_confirmation=(high_risk or not confirmed),
            allowed_to_drive_high_risk_action=(confirmed and not high_risk),
        )

    def _trust_delta(self, signal: InteractionSignal) -> float:
        if "trust_delta" in signal.metadata:
            return float(signal.metadata["trust_delta"])
        if signal.signal_type == SignalType.CORRECTION:
            return -0.03
        if signal.signal_type == SignalType.CONFIRMATION:
            return 0.04
        return 0.0

    def _boundary_confidence(
        self,
        known_topics: set[str],
        uncertain_topics: set[str],
        missing_topics: set[str],
        signals: list[InteractionSignal],
    ) -> float:
        explicit_evidence = sum(len(signal.evidence_refs) for signal in signals)
        base = 0.35 + min(0.35, 0.05 * (len(known_topics) + len(missing_topics)))
        ambiguity_penalty = min(0.2, 0.03 * len(uncertain_topics))
        evidence_bonus = min(0.2, 0.04 * explicit_evidence)
        return round(self._bounded(base - ambiguity_penalty + evidence_bonus), 3)

    def _interaction_state(
        self,
        active_hypotheses: list[IntentHypothesis],
        confirmed_intents: list[IntentHypothesis],
    ) -> Literal["probing", "confirming", "collaborating", "blocked"]:
        if any(item.high_risk and item.requires_environment_confirmation for item in [*active_hypotheses, *confirmed_intents]):
            return "confirming"
        if active_hypotheses:
            return "confirming"
        if confirmed_intents:
            return "collaborating"
        return "probing"

    def _strategy(
        self,
        *,
        entity_type: EntityType,
        knowledge_depth: str,
        tolerance_for_detail: str,
        active_hypotheses: list[IntentHypothesis],
        confirmed_intents: list[IntentHypothesis],
        missing_topics: list[str],
    ) -> CommunicationStrategy:
        has_high_risk = any(
            item.high_risk and item.requires_environment_confirmation
            for item in [*active_hypotheses, *confirmed_intents]
        )
        if has_high_risk:
            return CommunicationStrategy(
                explanation_granularity="step_by_step",
                collaboration_mode="confirm_first",
                requires_confirmation_before_high_risk=True,
                rationale="high_risk_intent_hypothesis_requires_environment_confirmation",
            )
        if missing_topics or knowledge_depth == "novice" or tolerance_for_detail == "low":
            return CommunicationStrategy(
                explanation_granularity="step_by_step",
                collaboration_mode="teach_and_confirm",
                requires_confirmation_before_high_risk=True,
                rationale="knowledge_boundary_has_missing_topics",
            )
        if entity_type == EntityType.AGENT and knowledge_depth in {"working", "expert"}:
            return CommunicationStrategy(
                explanation_granularity="brief",
                collaboration_mode="delegate_with_constraints",
                requires_confirmation_before_high_risk=True,
                rationale="agent_capability_boundary_is_sufficient_for_constrained_delegation",
            )
        return CommunicationStrategy(
            explanation_granularity="expert" if knowledge_depth == "expert" else "balanced",
            collaboration_mode="direct_collaboration",
            requires_confirmation_before_high_risk=True,
            rationale="confirmed_or_low_risk_context_supports_direct_collaboration",
        )

    def _replace_intent(
        self,
        intents: list[IntentHypothesis],
        replacement: IntentHypothesis,
    ) -> list[IntentHypothesis]:
        return [item for item in intents if item.content != replacement.content] + [replacement]

    def _choose_latest_vote(self, votes: list[str], default: str) -> Any:
        return votes[-1] if votes else default

    def _bounded(self, value: float) -> float:
        return max(0.0, min(1.0, value))


_DEFAULT_ENGINE = TheoryOfMindEngine()


def get_theory_of_mind_engine() -> TheoryOfMindEngine:
    return _DEFAULT_ENGINE
