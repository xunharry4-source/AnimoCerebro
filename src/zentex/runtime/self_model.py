from __future__ import annotations

"""
Living self-model layer for Zentex.

This module maintains the brain's dynamic self portrait: cognitive load,
recent weaknesses, recent strengths, confidence drift, and posture
recommendations. It is an internal state engine only and must not trigger
external actions or host-side messages.

LivingSelfModelEngine / 活的自我模型引擎

EN:
LivingSelfModelEngine is the internal self-portrait engine. It tracks cognitive
load, repeated weakness patterns, confidence drift, and posture adjustments.

The identity-facing substrate behind this self model is expected to evolve
through Identity Package Plugins. These packages may contribute role identity,
prohibitions, and domain experience while preserving isolation and rollback
semantics for contamination control.

ZH:
LivingSelfModelEngine（活的自我模型引擎）：负责维护大脑内部的状态特征与动态
自我画像，不直接触发任何外部动作执行或发送外部消息。

其背后的身份连续性底座将进一步通过 Identity Package Plugins（身份与经验包
插件家族）演进。角色包、禁令包、行业经验包都可以独立加载与回滚，并保持隔离
与防污染能力。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from typing_extensions import Self
from uuid import uuid4


@dataclass(frozen=True)
class CognitiveStateProfile:
    load_level: str
    stability_level: str
    exploration_mode: str
    reasoning_posture: str
    evidence_posture: str


@dataclass(frozen=True)
class RecentWeaknessPattern:
    pattern_id: str
    pattern_type: str
    frequency: int
    severity: str


@dataclass(frozen=True)
class ConfidenceDriftIndicator:
    statement_confidence: float
    evidence_support: float
    drift_score: float


@dataclass(frozen=True)
class LivingSelfModel:
    current_state: CognitiveStateProfile
    recent_strengths: List[str]
    recent_weaknesses: List[RecentWeaknessPattern]
    current_cognitive_load: str


class LivingSelfModelEngine:
    """
    Maintains the brain's dynamic self portrait.

    Hard rules:
    - continuous failures reduce risk tolerance and push posture to conservative
    - high-confidence low-evidence states must generate a drift indicator and a
      more conservative evidence posture
    - high cognitive load should emit a recommendation to lower active focus
      limits for attention control
    - no external actions are triggered from this engine

    Pluginization boundary:
    - identity and experience layers may be provided by Identity Package Plugins
    - this engine converts those inputs into runtime self-state traits
    - it does not directly load packages, execute plugins, or emit host actions
    - identity-package failures must stay isolated from self-state computation
    - package switches must support rollback and auditable revocation
    """

    def update_self_model(
        self,
        *,
        current_state: Any,
        recent_strengths: List[str] | None = None,
        recent_weaknesses: List[RecentWeaknessPattern] | None = None,
        current_cognitive_load: Optional[str] = None,
        failure_signals: Any = None,
        confidence_signals: Any = None,
    ) -> Tuple[LivingSelfModel, Optional[ConfidenceDriftIndicator], Dict[str, Any]]:
        state_profile = self._coerce_state_profile(current_state)
        weaknesses = list(recent_weaknesses or [])
        strengths = list(recent_strengths or [])
        recommendations: Dict[str, Any] = {}
        drift_indicator: Optional[ConfidenceDriftIndicator] = None

        failure_count = self._extract_failure_count(failure_signals)
        if failure_count >= 2:
            state_profile = CognitiveStateProfile(
                load_level=state_profile.load_level,
                stability_level="unstable",
                exploration_mode=state_profile.exploration_mode,
                reasoning_posture="conservative",
                evidence_posture="strict",
            )
            weaknesses.append(
                RecentWeaknessPattern(
                    pattern_id=str(uuid4()),
                    pattern_type="continuous_failures",
                    frequency=failure_count,
                    severity="high",
                )
            )
            recommendations["risk_tolerance"] = "lower"

        drift_indicator = self._detect_confidence_drift(confidence_signals)
        if drift_indicator is not None:
            state_profile = CognitiveStateProfile(
                load_level=state_profile.load_level,
                stability_level=state_profile.stability_level,
                exploration_mode=state_profile.exploration_mode,
                reasoning_posture="conservative",
                evidence_posture="strict",
            )
            weaknesses.append(
                RecentWeaknessPattern(
                    pattern_id=str(uuid4()),
                    pattern_type="overconfidence",
                    frequency=1,
                    severity="high" if drift_indicator.drift_score >= 0.5 else "medium",
                )
            )
            recommendations["expression_posture"] = "more_conservative"

        effective_load = current_cognitive_load or state_profile.load_level
        if effective_load == "high":
            recommendations["attention_budget_cap"] = {
                "suggested_max_active_focus": 2,
                "reason": "high_cognitive_load",
            }

        model = LivingSelfModel(
            current_state=state_profile,
            recent_strengths=strengths,
            recent_weaknesses=weaknesses,
            current_cognitive_load=effective_load,
        )
        return model, drift_indicator, recommendations

    def _detect_confidence_drift(self, confidence_signals: Any) -> Optional[ConfidenceDriftIndicator]:
        signal_dict = self._coerce_dict(confidence_signals)
        if not signal_dict:
            return None

        statement_confidence = self._coerce_float(signal_dict.get("statement_confidence"), default=0.0)
        evidence_support = self._coerce_float(signal_dict.get("evidence_support"), default=0.0)
        drift_score = max(0.0, statement_confidence - evidence_support)

        # High-confidence / low-evidence states are treated as confidence drift.
        if statement_confidence >= 0.7 and evidence_support <= 0.4 and drift_score >= 0.25:
            return ConfidenceDriftIndicator(
                statement_confidence=statement_confidence,
                evidence_support=evidence_support,
                drift_score=drift_score,
            )
        return None

    def _coerce_state_profile(self, value: Any) -> CognitiveStateProfile:
        if isinstance(value, CognitiveStateProfile):
            return value
        value_dict = self._coerce_dict(value)
        return CognitiveStateProfile(
            load_level=str(value_dict.get("load_level", "medium")),
            stability_level=str(value_dict.get("stability_level", "stable")),
            exploration_mode=str(value_dict.get("exploration_mode", "limited")),
            reasoning_posture=str(value_dict.get("reasoning_posture", "balanced")),
            evidence_posture=str(value_dict.get("evidence_posture", "normal")),
        )

    def _extract_failure_count(self, failure_signals: Any) -> int:
        signal_dict = self._coerce_dict(failure_signals)
        count = signal_dict.get("consecutive_failures", 0)
        try:
            return int(count)
        except (TypeError, ValueError):
            return 0

    def _coerce_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        if hasattr(value, "__dict__"):
            return dict(vars(value))
        return {}

    def _coerce_float(self, value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
