from __future__ import annotations

"""Feature 53 LivingSelfModelEngine.

The engine is intentionally deterministic. It converts turn results, recent
events, evidence support, and working-memory pressure into a living self-model
without consulting an LLM or external service.
"""

import hashlib
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from zentex.foundation.meta import TURN_MAX_DURATION_SECONDS

UTC = timezone.utc

_TURN_MAX_DURATION_MS: float = float(TURN_MAX_DURATION_SECONDS * 1000)
_STABILITY_DEGRADATION_PER_ERROR: float = 0.05
_STABILITY_MIN: float = 0.0
_STABILITY_MAX: float = 1.0
_CONFIDENCE_MIN: float = -1.0
_CONFIDENCE_MAX: float = 1.0
_LOAD_WINDOW: int = 5


@dataclass
class CognitiveStateProfile:
    load_level: str = "low"
    stability_level: str = "stable"
    exploration_mode: str = "open"
    reasoning_posture: str = "balanced"
    evidence_posture: str = "evidence_first"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecentWeaknessPattern:
    pattern_id: str
    pattern_type: str
    evidence_refs: list[str]
    frequency: int
    severity: str
    last_seen_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfidenceDriftIndicator:
    indicator_id: str
    statement_confidence: float
    evidence_support: float
    drift_score: float
    triggered_alert: bool
    created_at: str
    statement_id: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmotionLikeSignal:
    signal_id: str
    signal_type: str
    intensity: float
    evidence_refs: list[str]
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LivingSelfModel:
    model_id: str
    identity_anchor_ref: str
    current_state: CognitiveStateProfile
    recent_strengths: list[str] = field(default_factory=list)
    recent_weaknesses: list[RecentWeaknessPattern] = field(default_factory=list)
    current_risk_tolerance: str = "medium"
    current_uncertainty_tolerance: str = "medium"
    current_confidence_style: str = "balanced"
    current_cognitive_load: str = "low"
    last_updated_at: str = ""
    confidence_drift_indicators: list[ConfidenceDriftIndicator] = field(default_factory=list)
    emotion_like_signals: list[EmotionLikeSignal] = field(default_factory=list)
    update_sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "identity_anchor_ref": self.identity_anchor_ref,
            "current_state": self.current_state.to_dict(),
            "recent_strengths": list(self.recent_strengths),
            "recent_weaknesses": [item.to_dict() for item in self.recent_weaknesses],
            "current_risk_tolerance": self.current_risk_tolerance,
            "current_uncertainty_tolerance": self.current_uncertainty_tolerance,
            "current_confidence_style": self.current_confidence_style,
            "current_cognitive_load": self.current_cognitive_load,
            "last_updated_at": self.last_updated_at,
            "confidence_drift_indicators": [item.to_dict() for item in self.confidence_drift_indicators],
            "emotion_like_signals": [item.to_dict() for item in self.emotion_like_signals],
            "update_sources": list(self.update_sources),
        }


class SelfModelEngine:
    """Maintains legacy self metrics and the Feature 53 living self-model."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._cognitive_load: float = 0.0
        self._stability_score: float = 1.0
        self._confidence_drift: float = 0.0
        self._turn_durations: list[float] = []
        self._lock = threading.Lock()
        now = _now()
        self._living_model = LivingSelfModel(
            model_id=f"living-self:{session_id}",
            identity_anchor_ref=f"identity-anchor:{session_id}",
            current_state=CognitiveStateProfile(),
            last_updated_at=now,
            update_sources=[
                {
                    "source_type": "session_init",
                    "source_ref": session_id,
                    "observed_at": now,
                }
            ],
        )

    def record_turn(self, duration_ms: float, phase_error_count: int) -> None:
        with self._lock:
            self._turn_durations.append(duration_ms)
            window = self._turn_durations[-_LOAD_WINDOW:]
            avg_ms = sum(window) / len(window)
            raw_load = avg_ms / _TURN_MAX_DURATION_MS
            self._cognitive_load = min(raw_load, 1.0)
            if phase_error_count > 0:
                degradation = _STABILITY_DEGRADATION_PER_ERROR * phase_error_count
                self._stability_score = max(_STABILITY_MIN, self._stability_score - degradation)
            self._apply_numeric_legacy_state_locked()

    def update_confidence(self, delta: float) -> None:
        with self._lock:
            new_val = self._confidence_drift + delta
            self._confidence_drift = max(_CONFIDENCE_MIN, min(_CONFIDENCE_MAX, new_val))

    def reset_drift(self) -> None:
        with self._lock:
            self._confidence_drift = 0.0

    def update_from_turn_result(
        self,
        turn_result: dict[str, Any],
        *,
        recent_events: Optional[list[dict[str, Any]]] = None,
        working_memory_frame: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if not isinstance(turn_result, dict) or not turn_result:
            raise ValueError("turn_result must be a non-empty dict")
        with self._lock:
            sources: list[dict[str, Any]] = []
            now = _now()
            phase_error_count = int(turn_result.get("phase_error_count") or turn_result.get("error_count") or 0)
            duration_ms = float(turn_result.get("duration_ms") or 0.0)
            if duration_ms > 0:
                self._turn_durations.append(duration_ms)
                window = self._turn_durations[-_LOAD_WINDOW:]
                self._cognitive_load = min((sum(window) / len(window)) / _TURN_MAX_DURATION_MS, 1.0)
            if phase_error_count > 0:
                self._stability_score = max(
                    _STABILITY_MIN,
                    self._stability_score - (_STABILITY_DEGRADATION_PER_ERROR * phase_error_count),
                )
            load_source: dict[str, Any] | None = None
            if working_memory_frame is not None:
                load_source = self._apply_load_adjustment_locked(working_memory_frame)
                sources.append(load_source)
            patterns = self._detect_weakness_pattern_locked(recent_events or [])
            if patterns:
                self._merge_weaknesses_locked(patterns)
                sources.append(
                    {
                        "source_type": "recent_events",
                        "source_ref": trace_id or turn_result.get("turn_id") or "recent_events",
                        "pattern_count": len(patterns),
                        "observed_at": now,
                    }
                )
            drift_alert = any(item.triggered_alert for item in self._living_model.confidence_drift_indicators[-5:])
            failed = bool(turn_result.get("failed")) or str(turn_result.get("status") or "").lower() in {"failed", "error"}
            risk_hit = bool(turn_result.get("risk_hit") or turn_result.get("conflict_detected"))
            self._living_model.recent_strengths = _merge_unique(
                self._living_model.recent_strengths,
                self._strengths_from_turn(turn_result),
                max_items=8,
            )
            self._recompute_state_locked(failed=failed, risk_hit=risk_hit, drift_alert=drift_alert)
            self._living_model.update_sources = _merge_sources(
                self._living_model.update_sources,
                sources
                + [
                    {
                        "source_type": "turn_result",
                        "source_ref": turn_result.get("turn_id") or trace_id or "turn_result",
                        "status": turn_result.get("status"),
                        "failed": failed,
                        "phase_error_count": phase_error_count,
                        "observed_at": now,
                    }
                ],
            )
            if failed or risk_hit or drift_alert or load_source:
                self._append_signal_locked(
                    signal_type=_signal_type(failed=failed, risk_hit=risk_hit, drift_alert=drift_alert),
                    intensity=_signal_intensity(failed=failed, risk_hit=risk_hit, drift_alert=drift_alert),
                    evidence_refs=_event_evidence_refs(recent_events or []) or _listify(turn_result.get("evidence_refs")),
                )
            self._living_model.last_updated_at = now
            return {
                "feature_code": "B2-53",
                "operation": "update_from_turn_result",
                "living_self_model_status": "updated",
                "deterministic": True,
                "llm_required": False,
                "living_self_model": self._living_model.to_dict(),
                "detected_weakness_patterns": [item.to_dict() for item in patterns],
            }

    def detect_weakness_pattern(self, recent_events: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            patterns = self._detect_weakness_pattern_locked(recent_events)
            self._merge_weaknesses_locked(patterns)
            self._living_model.last_updated_at = _now()
            if patterns:
                self._living_model.update_sources = _merge_sources(
                    self._living_model.update_sources,
                    [
                        {
                            "source_type": "recent_events",
                            "source_ref": "weakness_detection",
                            "pattern_count": len(patterns),
                            "observed_at": self._living_model.last_updated_at,
                        }
                    ],
                )
                self._recompute_state_locked(failed=True, risk_hit=False, drift_alert=False)
            return {
                "feature_code": "B2-53",
                "operation": "detect_weakness_pattern",
                "living_self_model_status": "weakness_patterns_checked",
                "deterministic": True,
                "llm_required": False,
                "weakness_patterns": [item.to_dict() for item in patterns],
                "living_self_model": self._living_model.to_dict(),
            }

    def check_confidence_drift(
        self,
        statements: list[dict[str, Any]],
        evidence: Optional[Any] = None,
        *,
        threshold: float = 0.25,
    ) -> dict[str, Any]:
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be > 0 and <= 1")
        with self._lock:
            indicator = self._build_confidence_indicator(statements, evidence, threshold=threshold)
            if indicator is not None:
                self._living_model.confidence_drift_indicators.append(indicator)
                self._living_model.confidence_drift_indicators = self._living_model.confidence_drift_indicators[-20:]
                self._confidence_drift = max(_CONFIDENCE_MIN, min(_CONFIDENCE_MAX, indicator.drift_score))
                if indicator.triggered_alert:
                    self._living_model.current_confidence_style = "cautious"
                    self._living_model.current_state.evidence_posture = "evidence_first"
                    self._append_signal_locked(
                        signal_type="suspicion",
                        intensity=indicator.drift_score,
                        evidence_refs=indicator.evidence_refs,
                    )
            self._living_model.update_sources = _merge_sources(
                self._living_model.update_sources,
                [
                    {
                        "source_type": "confidence_drift_check",
                        "source_ref": indicator.indicator_id if indicator else "no_drift",
                        "triggered_alert": bool(indicator and indicator.triggered_alert),
                        "observed_at": _now(),
                    }
                ],
            )
            self._living_model.last_updated_at = _now()
            self._recompute_state_locked(
                failed=False,
                risk_hit=False,
                drift_alert=bool(indicator and indicator.triggered_alert),
            )
            return {
                "feature_code": "B2-53",
                "operation": "check_confidence_drift",
                "living_self_model_status": "confidence_drift_checked",
                "deterministic": True,
                "llm_required": False,
                "indicator": indicator.to_dict() if indicator else None,
                "living_self_model": self._living_model.to_dict(),
            }

    def apply_load_adjustment(self, working_memory_frame: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            adjustment = self._apply_load_adjustment_locked(working_memory_frame)
            self._living_model.update_sources = _merge_sources(self._living_model.update_sources, [adjustment])
            self._living_model.last_updated_at = _now()
            self._recompute_state_locked(failed=False, risk_hit=False, drift_alert=False)
            return {
                "feature_code": "B2-53",
                "operation": "apply_load_adjustment",
                "living_self_model_status": "load_adjusted",
                "deterministic": True,
                "llm_required": False,
                "load_adjustment": adjustment,
                "living_self_model": self._living_model.to_dict(),
            }

    def living_model_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._living_model.to_dict()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self._session_id,
                "cognitive_load": self._cognitive_load,
                "stability_score": self._stability_score,
                "confidence_drift": self._confidence_drift,
                "turn_count": len(self._turn_durations),
                "living_self_model": self._living_model.to_dict(),
                "current_cognitive_load": self._living_model.current_cognitive_load,
                "load_level": self._living_model.current_state.load_level,
                "stability_level": self._living_model.current_state.stability_level,
                "reasoning_posture": self._living_model.current_state.reasoning_posture,
                "recent_weaknesses": [item.to_dict() for item in self._living_model.recent_weaknesses],
            }

    def _apply_numeric_legacy_state_locked(self) -> None:
        if self._cognitive_load >= 0.75:
            self._living_model.current_state.load_level = "high"
        elif self._cognitive_load >= 0.35:
            self._living_model.current_state.load_level = "medium"
        else:
            self._living_model.current_state.load_level = "low"
        self._living_model.current_cognitive_load = self._living_model.current_state.load_level
        self._living_model.current_state.stability_level = "fragile" if self._stability_score < 0.6 else "stable"
        self._living_model.last_updated_at = _now()

    def _apply_load_adjustment_locked(self, working_memory_frame: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(working_memory_frame, dict) or not working_memory_frame:
            raise ValueError("working_memory_frame must be a non-empty dict")
        budget = working_memory_frame.get("attention_budget") or {}
        active = len(working_memory_frame.get("active_focus_ids") or working_memory_frame.get("active_items") or [])
        suspended = len(working_memory_frame.get("suspended_focus_ids") or working_memory_frame.get("suspended_items") or [])
        events = len(working_memory_frame.get("attention_shift_events") or [])
        max_active = max(1, int(budget.get("max_active_focus") or max(active, 1)))
        pressure = min(1.0, (active / max_active) + (suspended * 0.15) + (events * 0.1))
        if pressure >= 0.85:
            load_level = "high"
        elif pressure >= 0.45:
            load_level = "medium"
        else:
            load_level = "low"
        self._living_model.current_state.load_level = load_level
        self._living_model.current_cognitive_load = load_level
        if load_level == "high":
            self._living_model.current_state.reasoning_posture = "conservative"
            self._living_model.current_state.exploration_mode = "limited"
        return {
            "source_type": "working_memory_frame",
            "source_ref": working_memory_frame.get("frame_id") or working_memory_frame.get("tick_id") or "working_memory_frame",
            "active_focus_count": active,
            "suspended_focus_count": suspended,
            "attention_shift_event_count": events,
            "pressure_score": round(pressure, 4),
            "load_level": load_level,
            "observed_at": _now(),
        }

    def _detect_weakness_pattern_locked(self, recent_events: list[dict[str, Any]]) -> list[RecentWeaknessPattern]:
        if not isinstance(recent_events, list):
            raise ValueError("recent_events must be a list")
        grouped: dict[str, dict[str, Any]] = {}
        for event in recent_events:
            if not isinstance(event, dict):
                raise ValueError("recent_events items must be dicts")
            evidence_refs = _listify(event.get("evidence_refs"))
            if not evidence_refs:
                continue
            key = str(
                event.get("weakness_type")
                or event.get("pattern_type")
                or event.get("error_code")
                or event.get("conflict_type")
                or event.get("event_type")
                or "unclassified_weakness"
            )
            bucket = grouped.setdefault(key, {"evidence_refs": [], "frequency": 0, "severity_rank": 0, "last_seen_at": ""})
            bucket["frequency"] += 1
            bucket["evidence_refs"] = _merge_unique(bucket["evidence_refs"], evidence_refs, max_items=12)
            bucket["severity_rank"] = max(bucket["severity_rank"], _severity_rank(str(event.get("severity") or "medium")))
            bucket["last_seen_at"] = str(event.get("observed_at") or event.get("timestamp") or _now())
        patterns: list[RecentWeaknessPattern] = []
        for pattern_type, bucket in grouped.items():
            if bucket["frequency"] < 3:
                continue
            severity = _severity_from_rank(bucket["severity_rank"], bucket["frequency"])
            patterns.append(
                RecentWeaknessPattern(
                    pattern_id=_stable_id("weakness", self._session_id, pattern_type, ",".join(bucket["evidence_refs"])),
                    pattern_type=pattern_type,
                    evidence_refs=bucket["evidence_refs"],
                    frequency=bucket["frequency"],
                    severity=severity,
                    last_seen_at=bucket["last_seen_at"],
                )
            )
        patterns.sort(key=lambda item: (item.frequency, _severity_rank(item.severity)), reverse=True)
        return patterns

    def _merge_weaknesses_locked(self, patterns: list[RecentWeaknessPattern]) -> None:
        existing = {item.pattern_type: item for item in self._living_model.recent_weaknesses}
        for pattern in patterns:
            current = existing.get(pattern.pattern_type)
            if current is None:
                existing[pattern.pattern_type] = pattern
                continue
            current.frequency = max(current.frequency, pattern.frequency)
            current.severity = _severity_from_rank(
                max(_severity_rank(current.severity), _severity_rank(pattern.severity)),
                current.frequency,
            )
            current.evidence_refs = _merge_unique(current.evidence_refs, pattern.evidence_refs, max_items=12)
            current.last_seen_at = max(current.last_seen_at, pattern.last_seen_at)
        merged = list(existing.values())
        merged.sort(key=lambda item: (item.frequency, _severity_rank(item.severity)), reverse=True)
        self._living_model.recent_weaknesses = merged[:12]

    def _build_confidence_indicator(
        self,
        statements: list[dict[str, Any]],
        evidence: Optional[Any],
        *,
        threshold: float,
    ) -> Optional[ConfidenceDriftIndicator]:
        if not isinstance(statements, list):
            raise ValueError("statements must be a list")
        best: ConfidenceDriftIndicator | None = None
        for statement in statements:
            if not isinstance(statement, dict):
                raise ValueError("statements items must be dicts")
            confidence = _clamp01(float(statement.get("confidence") or statement.get("statement_confidence") or 0.0))
            support = _clamp01(
                float(
                    statement.get("evidence_support")
                    if statement.get("evidence_support") is not None
                    else _support_for_statement(statement, evidence)
                )
            )
            drift = max(0.0, round(confidence - support, 4))
            evidence_refs = _merge_unique(_listify(statement.get("evidence_refs")), _evidence_refs_for_statement(statement, evidence))
            candidate = ConfidenceDriftIndicator(
                indicator_id=_stable_id(
                    "confidence-drift",
                    self._session_id,
                    str(statement.get("statement_id") or statement.get("id") or statement.get("text") or ""),
                    str(confidence),
                    str(support),
                ),
                statement_id=str(statement.get("statement_id") or statement.get("id") or ""),
                statement_confidence=confidence,
                evidence_support=support,
                drift_score=drift,
                triggered_alert=drift >= threshold,
                evidence_refs=evidence_refs,
                created_at=_now(),
            )
            if best is None or candidate.drift_score > best.drift_score:
                best = candidate
        if best is None or not best.triggered_alert:
            return None
        return best

    def _recompute_state_locked(self, *, failed: bool, risk_hit: bool, drift_alert: bool) -> None:
        load = self._living_model.current_state.load_level
        has_repeated_weakness = any(item.frequency >= 3 for item in self._living_model.recent_weaknesses)
        if failed or risk_hit or has_repeated_weakness:
            self._living_model.current_state.stability_level = "fragile"
        elif self._stability_score < 0.8:
            self._living_model.current_state.stability_level = "recovering"
        else:
            self._living_model.current_state.stability_level = "stable"
        if load == "high" or drift_alert or has_repeated_weakness:
            self._living_model.current_state.reasoning_posture = "conservative"
            self._living_model.current_state.exploration_mode = "limited"
            self._living_model.current_risk_tolerance = "low"
        elif self._living_model.current_state.stability_level == "stable":
            self._living_model.current_state.reasoning_posture = "balanced"
            self._living_model.current_state.exploration_mode = "open"
            self._living_model.current_risk_tolerance = "medium"
        self._living_model.current_uncertainty_tolerance = "low" if drift_alert else "medium"
        if drift_alert:
            self._living_model.current_confidence_style = "cautious"
            self._living_model.current_state.evidence_posture = "evidence_first"

    def _append_signal_locked(self, *, signal_type: str, intensity: float, evidence_refs: list[str]) -> None:
        signal = EmotionLikeSignal(
            signal_id=_stable_id("emotion-signal", self._session_id, signal_type, _now(), ",".join(evidence_refs)),
            signal_type=signal_type,
            intensity=round(_clamp01(intensity), 4),
            evidence_refs=evidence_refs,
            expires_at=(datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        )
        self._living_model.emotion_like_signals.append(signal)
        self._living_model.emotion_like_signals = self._living_model.emotion_like_signals[-20:]

    def _strengths_from_turn(self, turn_result: dict[str, Any]) -> list[str]:
        strengths: list[str] = []
        if _listify(turn_result.get("evidence_refs")):
            strengths.append("evidence_traceability")
        if bool(turn_result.get("recovered")) or str(turn_result.get("recovery_status") or "").lower() == "recovered":
            strengths.append("recovery_capacity")
        if str(turn_result.get("status") or "").lower() in {"completed", "success", "ok"}:
            strengths.append("execution_completion")
        return strengths

    def __repr__(self) -> str:
        snap = self.snapshot()
        return (
            f"SelfModelEngine(session_id={snap['session_id']!r}, "
            f"load={snap['cognitive_load']:.2f}, stability={snap['stability_score']:.2f})"
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, set):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _merge_unique(existing: list[str], incoming: list[str], *, max_items: int = 20) -> list[str]:
    merged: list[str] = []
    for item in list(existing) + list(incoming):
        if item and item not in merged:
            merged.append(item)
    return merged[-max_items:]


def _merge_sources(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], *, max_items: int = 30) -> list[dict[str, Any]]:
    merged = list(existing)
    for item in incoming:
        if item:
            merged.append(item)
    return merged[-max_items:]


def _event_evidence_refs(events: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for event in events:
        refs = _merge_unique(refs, _listify(event.get("evidence_refs")))
    return refs


def _signal_type(*, failed: bool, risk_hit: bool, drift_alert: bool) -> str:
    if drift_alert:
        return "suspicion"
    if risk_hit:
        return "alert"
    if failed:
        return "tension"
    return "stable"


def _signal_intensity(*, failed: bool, risk_hit: bool, drift_alert: bool) -> float:
    if drift_alert:
        return 0.9
    if risk_hit:
        return 0.75
    if failed:
        return 0.6
    return 0.25


def _severity_rank(severity: str) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(severity.lower(), 2)


def _severity_from_rank(rank: int, frequency: int) -> str:
    effective = max(rank, 3 if frequency >= 3 else 2)
    if effective >= 4:
        return "critical"
    if effective >= 3:
        return "high"
    if effective >= 2:
        return "medium"
    return "low"


def _support_for_statement(statement: dict[str, Any], evidence: Optional[Any]) -> float:
    statement_id = str(statement.get("statement_id") or statement.get("id") or "")
    if isinstance(evidence, dict):
        if "support" in evidence:
            return float(evidence["support"])
        if statement_id and statement_id in evidence and isinstance(evidence[statement_id], dict):
            return float(evidence[statement_id].get("support", 0.0))
    if isinstance(evidence, list):
        matches = [item for item in evidence if isinstance(item, dict) and str(item.get("statement_id") or "") == statement_id]
        if matches:
            return max(float(item.get("support", 0.0)) for item in matches)
    return 0.0


def _evidence_refs_for_statement(statement: dict[str, Any], evidence: Optional[Any]) -> list[str]:
    statement_id = str(statement.get("statement_id") or statement.get("id") or "")
    refs: list[str] = []
    if isinstance(evidence, dict):
        refs = _merge_unique(refs, _listify(evidence.get("evidence_refs")))
        if statement_id and isinstance(evidence.get(statement_id), dict):
            refs = _merge_unique(refs, _listify(evidence[statement_id].get("evidence_refs")))
    elif isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict) and (not statement_id or str(item.get("statement_id") or "") == statement_id):
                refs = _merge_unique(refs, _listify(item.get("evidence_refs")))
    return refs
