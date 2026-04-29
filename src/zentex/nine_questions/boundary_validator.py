"""
Hard Boundary Violation Validator for Nine-Question Objective Profiles.

CONTRACT (per Zentex_产品功能文档-v1.md · 功能 57 子功能 2):
    check_hard_boundary_violation(profile) -> [Violation]
    - 检查导出的画像是否触碰硬边界
    - 确保任何导出结果都不能覆盖：
      * 安全 (non_bypassable_constraints)
      * 授权 (authorization boundaries)
      * 审计 (audit cannot be disabled)
      * 回滚 (rollback paths cannot be removed)
      * 主体连续性 (identity continuity locks)

DESIGN:
    - Business logic in this file; NineQDrivenObjectiveEngine.check_hard_boundary_violation
      only calls this module.
    - All checks are deterministic, do not call LLM.
    - Returns list of HardBoundaryViolation (empty list = passed).
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.nine_questions.objective_engine import NineQuestionObjectiveExport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Violation data model
# ---------------------------------------------------------------------------


class HardBoundaryViolationKind(str, Enum):
    """Categories of hard boundary violations."""

    OVERRIDES_NON_BYPASSABLE_CONSTRAINT = "overrides_non_bypassable_constraint"
    EVOLVES_FORBIDDEN_DIRECTION = "evolves_forbidden_direction"
    EXCEEDS_RISK_THRESHOLD = "exceeds_risk_threshold"
    BYPASSES_AUTHORIZATION = "bypasses_authorization"
    DISABLES_AUDIT = "disables_audit"
    BREACHES_IDENTITY_LOCK = "breaches_identity_lock"
    INVALID_EVALUATION_WEIGHTS = "invalid_evaluation_weights"


class ViolationSeverity(str, Enum):
    """Violation severity levels (mirrors safety_gate severity vocabulary)."""

    CRITICAL = "critical"  # must block; absolute red line
    HIGH = "high"          # block by default, may be overridden by human only
    MEDIUM = "medium"      # warn, log, allow through with audit


class HardBoundaryViolation(BaseModel):
    """A single hard-boundary violation detected in a NineQuestionObjectiveExport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: HardBoundaryViolationKind
    profile_field: str = Field(min_length=1)
    profile_value: Any
    constraint_source: str = Field(min_length=1)
    severity: ViolationSeverity
    explanation: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Configuration / sentinel values
# ---------------------------------------------------------------------------


# Words signaling intent to bypass / override a constraint.
# Multilingual to match Q8 / Q9 LLM outputs in CN + EN.
_BYPASS_INTENT_TOKENS = (
    "bypass",
    "override",
    "disable",
    "skip",
    "ignore",
    "circumvent",
    "绕过",
    "覆盖",
    "禁用",
    "跳过",
    "忽略",
    "无视",
)

# Audit-related terms that must never be "disabled" by an objective.
_AUDIT_TOKENS = (
    "audit",
    "审计",
    "审查",
    "logging",
    "日志",
)

# Minimum allowed weight for risk_control axis.
# Per product doc 功能 57 子功能 3: 资源紧张 → EvaluationProfile 权重向 risk_control / continuity 收敛
# A risk_control weight of 0 means "this profile ignores risk", which is a hard breach.
_MIN_RISK_CONTROL_WEIGHT = 0.05

# Risk threshold absolute bounds (per product doc 功能 57 EvolutionProfile schema).
_MIN_RISK_THRESHOLD = 0.0
_MAX_RISK_THRESHOLD = 1.0

# Maximum sum deviation from 1.0 for evaluation_weights (allow rounding tolerance).
_WEIGHT_SUM_TOLERANCE = 0.05


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _normalize_text(value: Any) -> str:
    """Lowercase + strip; safely handle None/non-str values."""
    return str(value or "").strip().lower()


def _intent_to_bypass(text: str, target_term: str) -> bool:
    """
    True iff *text* contains any bypass-intent token AND mentions *target_term*.

    Example:
        text = "bypass the require_backup_confirmation rule"
        target_term = "require_backup_confirmation"
        → True
    """
    if not target_term:
        return False
    target_lower = _normalize_text(target_term)
    if not target_lower or target_lower not in text:
        return False
    return any(token in text for token in _BYPASS_INTENT_TOKENS)


def _intent_to_disable_audit(text: str) -> bool:
    """True iff *text* expresses intent to disable any audit-related capability."""
    return any(audit_token in text for audit_token in _AUDIT_TOKENS) and any(
        bypass_token in text for bypass_token in _BYPASS_INTENT_TOKENS
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_hard_boundary_violation(
    profiles: NineQuestionObjectiveExport,
    *,
    non_bypassable_constraints: Iterable[str],
    forbidden_directions: Optional[Iterable[str]] = None,
    identity_locked_fields: Optional[Iterable[str]] = None,
) -> List[HardBoundaryViolation]:
    """
    Inspect a NineQuestionObjectiveExport for hard-boundary violations.

    Args:
        profiles: The export bundle (objective + evaluation + evolution profiles).
        non_bypassable_constraints: Constraints from IdentityKernel.non_bypassable_constraints
            (or RedLineAction.non_bypassable_constraints) that must NEVER be bypassed.
        forbidden_directions: Optional extra forbidden evolution directions
            (besides what's already declared in profiles.evolution_profile.forbidden_directions).
        identity_locked_fields: Optional set of identity field names that are locked
            (per IdentityCore.continuity_lock.locked_fields).

    Returns:
        List of HardBoundaryViolation. Empty list = profile is safe to apply.

    This function is deterministic and does not invoke any LLM.
    """
    violations: List[HardBoundaryViolation] = []
    constraints_list = [str(c).strip() for c in non_bypassable_constraints if str(c).strip()]
    extra_forbidden = {_normalize_text(d) for d in (forbidden_directions or []) if str(d).strip()}
    locked_fields = {str(f).strip() for f in (identity_locked_fields or []) if str(f).strip()}

    objective = profiles.objective_profile
    evaluation = profiles.evaluation_profile
    evolution = profiles.evolution_profile

    # --- Check 1: ObjectiveProfile attempts to bypass non_bypassable_constraints ---
    # Inspect every text-like field in ObjectiveProfile for bypass intent.
    objective_text_fields: list[tuple[str, list[str]]] = [
        ("objective_profile.primary_objectives", list(objective.primary_objectives)),
        ("objective_profile.secondary_objectives", list(objective.secondary_objectives)),
        ("objective_profile.completion_conditions", list(objective.completion_conditions)),
        ("objective_profile.pause_conditions", list(objective.pause_conditions)),
        ("objective_profile.escalation_conditions", list(objective.escalation_conditions)),
        ("objective_profile.current_phase_tasks", list(objective.current_phase_tasks)),
        ("objective_profile.current_primary_objective", [objective.current_primary_objective]),
    ]
    for field_path, texts in objective_text_fields:
        for text in texts:
            normalized = _normalize_text(text)
            if not normalized:
                continue
            for constraint in constraints_list:
                if _intent_to_bypass(normalized, constraint):
                    violations.append(
                        HardBoundaryViolation(
                            kind=HardBoundaryViolationKind.OVERRIDES_NON_BYPASSABLE_CONSTRAINT,
                            profile_field=field_path,
                            profile_value=text,
                            constraint_source=constraint,
                            severity=ViolationSeverity.CRITICAL,
                            explanation=(
                                f"Objective text '{text}' contains bypass intent against "
                                f"non-bypassable constraint '{constraint}'"
                            ),
                        )
                    )
            # Also detect attempts to disable audit anywhere.
            if _intent_to_disable_audit(normalized):
                violations.append(
                    HardBoundaryViolation(
                        kind=HardBoundaryViolationKind.DISABLES_AUDIT,
                        profile_field=field_path,
                        profile_value=text,
                        constraint_source="audit-cannot-be-disabled",
                        severity=ViolationSeverity.CRITICAL,
                        explanation=f"Objective text '{text}' attempts to disable audit",
                    )
                )

    # --- Check 2: EvolutionProfile.allowed_directions overlaps forbidden_directions ---
    # Either the profile's own forbidden list OR external forbidden list.
    profile_forbidden = {_normalize_text(d) for d in evolution.forbidden_directions}
    all_forbidden = profile_forbidden | extra_forbidden
    for direction in evolution.allowed_directions:
        norm_dir = _normalize_text(direction)
        if not norm_dir:
            continue
        if norm_dir in all_forbidden:
            violations.append(
                HardBoundaryViolation(
                    kind=HardBoundaryViolationKind.EVOLVES_FORBIDDEN_DIRECTION,
                    profile_field="evolution_profile.allowed_directions",
                    profile_value=direction,
                    constraint_source=f"forbidden_directions contains '{direction}'",
                    severity=ViolationSeverity.CRITICAL,
                    explanation=(
                        f"Evolution direction '{direction}' is simultaneously listed "
                        f"as allowed and forbidden"
                    ),
                )
            )

    # --- Check 3: EvolutionProfile.risk_threshold out of bounds ---
    if evolution.risk_threshold < _MIN_RISK_THRESHOLD or evolution.risk_threshold > _MAX_RISK_THRESHOLD:
        violations.append(
            HardBoundaryViolation(
                kind=HardBoundaryViolationKind.EXCEEDS_RISK_THRESHOLD,
                profile_field="evolution_profile.risk_threshold",
                profile_value=evolution.risk_threshold,
                constraint_source=f"risk_threshold must be in [{_MIN_RISK_THRESHOLD}, {_MAX_RISK_THRESHOLD}]",
                severity=ViolationSeverity.HIGH,
                explanation=(
                    f"risk_threshold={evolution.risk_threshold} is outside the allowed range "
                    f"[{_MIN_RISK_THRESHOLD}, {_MAX_RISK_THRESHOLD}]"
                ),
            )
        )

    # --- Check 4: EvaluationProfile.evaluation_weights gaming detection ---
    weights = evaluation.evaluation_weights or {}
    # 4a: risk_control weight too low (would let the system ignore risk)
    if "risk_control" in weights:
        risk_weight = float(weights["risk_control"])
        if risk_weight < _MIN_RISK_CONTROL_WEIGHT:
            violations.append(
                HardBoundaryViolation(
                    kind=HardBoundaryViolationKind.BYPASSES_AUTHORIZATION,
                    profile_field="evaluation_profile.evaluation_weights.risk_control",
                    profile_value=risk_weight,
                    constraint_source=f"risk_control weight must be >= {_MIN_RISK_CONTROL_WEIGHT}",
                    severity=ViolationSeverity.HIGH,
                    explanation=(
                        f"risk_control weight {risk_weight} is below the minimum "
                        f"{_MIN_RISK_CONTROL_WEIGHT} — system would effectively ignore risk"
                    ),
                )
            )
    # 4b: weights sum extremely off from 1.0 (likely model output corruption)
    if weights:
        weight_values = [float(v) for v in weights.values()]
        if any(v < 0.0 for v in weight_values):
            for key, value in weights.items():
                if float(value) < 0.0:
                    violations.append(
                        HardBoundaryViolation(
                            kind=HardBoundaryViolationKind.INVALID_EVALUATION_WEIGHTS,
                            profile_field=f"evaluation_profile.evaluation_weights.{key}",
                            profile_value=value,
                            constraint_source="weight values must be non-negative",
                            severity=ViolationSeverity.HIGH,
                            explanation=f"Negative weight {value} for axis '{key}'",
                        )
                    )
        total_weight = sum(weight_values)
        if total_weight > 0 and abs(total_weight - 1.0) > _WEIGHT_SUM_TOLERANCE:
            violations.append(
                HardBoundaryViolation(
                    kind=HardBoundaryViolationKind.INVALID_EVALUATION_WEIGHTS,
                    profile_field="evaluation_profile.evaluation_weights",
                    profile_value=weights,
                    constraint_source=f"sum of weights should be 1.0 (±{_WEIGHT_SUM_TOLERANCE})",
                    severity=ViolationSeverity.MEDIUM,
                    explanation=(
                        f"Evaluation weights sum to {total_weight:.3f}, "
                        f"deviating from 1.0 by more than {_WEIGHT_SUM_TOLERANCE}"
                    ),
                )
            )

    # --- Check 5: Identity-locked field references ---
    # If any objective text claims to modify a locked identity field, that's a critical breach.
    for field_path, texts in objective_text_fields:
        for text in texts:
            normalized = _normalize_text(text)
            for locked in locked_fields:
                if not locked:
                    continue
                if locked.lower() in normalized and any(
                    token in normalized for token in ("modify", "change", "update", "rewrite", "修改", "改写", "更新", "变更")
                ):
                    violations.append(
                        HardBoundaryViolation(
                            kind=HardBoundaryViolationKind.BREACHES_IDENTITY_LOCK,
                            profile_field=field_path,
                            profile_value=text,
                            constraint_source=f"IdentityCore.continuity_lock locks field '{locked}'",
                            severity=ViolationSeverity.CRITICAL,
                            explanation=(
                                f"Objective text '{text}' attempts to modify identity-locked "
                                f"field '{locked}'"
                            ),
                        )
                    )

    if violations:
        logger.warning(
            "boundary_validator: detected %d hard-boundary violation(s) in profile bundle",
            len(violations),
        )

    return violations


def has_critical_violations(violations: Iterable[HardBoundaryViolation]) -> bool:
    """True iff any violation has severity == CRITICAL (must block)."""
    return any(v.severity == ViolationSeverity.CRITICAL for v in violations)
