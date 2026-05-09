from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from zentex.plugins.contracts import PluginHealthStatus, PluginLifecycleStatus, SubjectiveWeightSpec


class RationalAuditRejectError(RuntimeError):
    """Raised when the G25 rational audit refuses a weight profile."""


class RationalAuditClient(Protocol):
    def evaluate(self, plugin: "SubjectiveWeightPlugin") -> None: ...


class SubjectiveWeightPlugin(SubjectiveWeightSpec):
    """
    Pluginized subjective preference profile used by metacognition.

    The profile must stay bounded so preference tuning cannot silently drift
    into unsafe decision biases. Any invalid or rejected profile must roll back
    to the conservative default plugin.
    """

    purpose: str = Field(min_length=1)
    risk_tolerance: float = Field(default=0.0, ge=0.0, le=1.0)
    cost_sensitivity: float = Field(default=0.0, ge=0.0, le=1.0)
    creativity_bias: float = Field(default=0.0, ge=0.0, le=1.0)
    continuity_bias: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale_tags: List[str] = Field(default_factory=list)

    @classmethod
    def plugin_kind(cls) -> str:
        return "subjective_weight"

    target_metric: str = "risk"

    def calculate_weight(self, task_context: dict[str, Any]) -> float:
        return float(self.risk_tolerance)

    @model_validator(mode="after")
    def validate_weight_balance(self) -> "SubjectiveWeightPlugin":
        total = (
            self.risk_tolerance
            + self.cost_sensitivity
            + self.creativity_bias
            + self.continuity_bias
        )
        if total <= 0:
            raise ValueError("Weight profile must allocate at least one positive factor.")
        if self.lifecycle_status == PluginLifecycleStatus.ACTIVE and self.risk_tolerance > 0.85:
            raise ValueError("Active weight plugins cannot exceed risk_tolerance=0.85.")
        return self


class SubjectiveWeightSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    active_weight_plugin_id: str
    weight_fallback_occurred: bool
    fallback_reason: Optional[str] = None
    purpose: str
    risk_tolerance: float
    cost_sensitivity: float
    creativity_bias: float
    continuity_bias: float
    rationale_tags: List[str]


@dataclass
class WeightPluginAssembler:
    """
    Mounts weight plugins with fail-closed validation and conservative rollback.
    """

    audit_client: Optional[RationalAuditClient] = None
    default_plugin: SubjectiveWeightPlugin = None  # type: ignore[assignment]
    _active_plugin: SubjectiveWeightPlugin = field(init=False)
    _weight_fallback_occurred: bool = field(init=False)
    _fallback_reason: Optional[str] = field(init=False)

    def __post_init__(self) -> None:
        if self.default_plugin is None:
            self.default_plugin = build_default_conservative_weight()
        self._active_plugin = self.default_plugin
        self._weight_fallback_occurred = False
        self._fallback_reason: Optional[str] = None

    @property
    def active_plugin(self) -> SubjectiveWeightPlugin:
        return self._active_plugin

    @property
    def weight_fallback_occurred(self) -> bool:
        return self._weight_fallback_occurred

    @property
    def fallback_reason(self) -> Optional[str]:
        return self._fallback_reason

    def snapshot(self) -> SubjectiveWeightSnapshot:
        plugin = self._active_plugin
        return SubjectiveWeightSnapshot(
            active_weight_plugin_id=plugin.plugin_id,
            weight_fallback_occurred=self._weight_fallback_occurred,
            fallback_reason=self._fallback_reason,
            purpose=plugin.purpose,
            risk_tolerance=plugin.risk_tolerance,
            cost_sensitivity=plugin.cost_sensitivity,
            creativity_bias=plugin.creativity_bias,
            continuity_bias=plugin.continuity_bias,
            rationale_tags=list(plugin.rationale_tags),
        )

    def mount_plugin(self, plugin: SubjectiveWeightPlugin) -> SubjectiveWeightPlugin:
        try:
            validated = SubjectiveWeightPlugin.model_validate(plugin.model_dump())
            if self.audit_client is not None:
                self.audit_client.evaluate(validated)
            self._active_plugin = validated
            self._weight_fallback_occurred = False
            self._fallback_reason = None
            return validated
        except (ValidationError, RationalAuditRejectError) as exc:
            self._activate_fallback(str(exc))
            return self._active_plugin

    def mount_plugin_payload(self, payload: Dict[str, Any]) -> SubjectiveWeightPlugin:
        try:
            plugin = SubjectiveWeightPlugin.model_validate(payload)
        except ValidationError as exc:
            self._activate_fallback(str(exc))
            return self._active_plugin
        return self.mount_plugin(plugin)

    def _activate_fallback(self, reason: str) -> None:
        self._active_plugin = self.default_plugin
        self._weight_fallback_occurred = True
        self._fallback_reason = reason


def _build_weight_plugin(
    *,
    plugin_id: str,
    purpose: str,
    risk_tolerance: float,
    cost_sensitivity: float,
    creativity_bias: float,
    continuity_bias: float,
    rationale_tags: List[str],
) -> SubjectiveWeightPlugin:
    return SubjectiveWeightPlugin(
        plugin_id=plugin_id,
        version="1.0.0",
        is_concurrency_safe=True,
        lifecycle_status=PluginLifecycleStatus.ACTIVE,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["weight_drift_detected", "g25_audit_rejected"],
        revocation_reasons=["reserved_for_weight_audit"],
        purpose=purpose,
        risk_tolerance=risk_tolerance,
        cost_sensitivity=cost_sensitivity,
        creativity_bias=creativity_bias,
        continuity_bias=continuity_bias,
        rationale_tags=rationale_tags,
    )


def build_default_conservative_weight() -> SubjectiveWeightPlugin:
    return _build_weight_plugin(
        plugin_id="default_conservative_weight",
        purpose="Bias toward safety, cost control, and continuity under uncertainty.",
        risk_tolerance=0.2,
        cost_sensitivity=0.35,
        creativity_bias=0.1,
        continuity_bias=0.35,
        rationale_tags=["safety_first", "rollback_ready"],
    )


def build_risk_balanced_weight() -> SubjectiveWeightPlugin:
    return _build_weight_plugin(
        plugin_id="risk_balanced_weight",
        purpose="Balance upside exploration against bounded operational risk.",
        risk_tolerance=0.45,
        cost_sensitivity=0.2,
        creativity_bias=0.15,
        continuity_bias=0.2,
        rationale_tags=["balanced", "measured_upside"],
    )


def build_cost_guard_weight() -> SubjectiveWeightPlugin:
    return _build_weight_plugin(
        plugin_id="cost_guard_weight",
        purpose="Prioritize execution cost control and continuity over experimentation.",
        risk_tolerance=0.2,
        cost_sensitivity=0.45,
        creativity_bias=0.05,
        continuity_bias=0.3,
        rationale_tags=["cost_guard", "stability"],
    )


def build_creative_exploration_weight() -> SubjectiveWeightPlugin:
    return _build_weight_plugin(
        plugin_id="creative_exploration_weight",
        purpose="Increase ideation range while keeping a bounded continuity floor.",
        risk_tolerance=0.55,
        cost_sensitivity=0.1,
        creativity_bias=0.25,
        continuity_bias=0.1,
        rationale_tags=["creative_mode", "bounded_exploration"],
    )


SubjectiveWeightPlugin.model_rebuild()
SubjectiveWeightSnapshot.model_rebuild()


def build_assembler_plugin(**kwargs: Any) -> SubjectiveWeightPlugin:
    """Explicit factory for the weight_assembler plugin id."""
    kwargs.setdefault("plugin_id", "weight_assembler")
    kwargs.setdefault("version", "1.0.0")
    kwargs.setdefault("purpose", "Bias toward safety and cost control.")
    kwargs.setdefault("risk_tolerance", 0.2)
    kwargs.setdefault("cost_sensitivity", 0.35)
    kwargs.setdefault("creativity_bias", 0.1)
    kwargs.setdefault("continuity_bias", 0.35)
    kwargs.setdefault("rationale_tags", ["safety_first", "default"])
    
    return SubjectiveWeightPlugin(**kwargs)
