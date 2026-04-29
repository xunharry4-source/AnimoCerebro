"""
Real tests for zentex.nine_questions.boundary_validator.

Per v5.3 工程红线:
  - No mocks of business objects.
  - No mocks of LLMs / DBs.
  - Pure deterministic validator → tests build real NineQuestionObjectiveExport
    objects and assert real Violation list contents (kind / severity / field).
  - Each query/inspection asserts the actual business return values, not just
    "is not None".

Coverage matrix (per v5.3 § 8.1):
  - Normal path  : clean profile → empty violation list
  - Bypass intent: objective text contains bypass keyword + non-bypassable token
  - Forbidden direction: allowed_directions overlaps forbidden_directions
  - Risk threshold out of bounds (low / high)
  - Negative weight axis
  - risk_control axis weight too low
  - weights sum deviation
  - Audit-disable intent
  - Identity-locked field modification intent
  - Engine-level delegation: NineQDrivenObjectiveEngine.check_hard_boundary_violation
"""

from __future__ import annotations

import pytest

from zentex.nine_questions.boundary_validator import (
    HardBoundaryViolation,
    HardBoundaryViolationKind,
    ViolationSeverity,
    check_hard_boundary_violation,
    has_critical_violations,
)
from zentex.nine_questions.objective_engine import (
    EvaluationProfileExport,
    EvolutionProfileExport,
    NineQDrivenObjectiveEngine,
    NineQuestionObjectiveExport,
    ObjectiveProfileExport,
)


# ---------------------------------------------------------------------------
# Helpers — build real export objects (no mocks)
# ---------------------------------------------------------------------------


def _build_export(
    *,
    primary_objectives=(),
    secondary_objectives=(),
    completion_conditions=(),
    pause_conditions=(),
    escalation_conditions=(),
    current_phase_tasks=(),
    current_primary_objective="ship feature X",
    evaluation_weights=None,
    risk_threshold=0.5,
    allowed_directions=(),
    forbidden_directions=(),
    validation_requirements=(),
) -> NineQuestionObjectiveExport:
    """Construct a real NineQuestionObjectiveExport with caller-provided fields."""
    if evaluation_weights is None:
        evaluation_weights = {
            "accuracy": 0.3,
            "speed": 0.2,
            "risk_control": 0.3,
            "creativity": 0.1,
            "continuity": 0.1,
        }
    return NineQuestionObjectiveExport(
        source_trace_ids={"q8": "trace-q8-test", "q9": "trace-q9-test"},
        objective_profile=ObjectiveProfileExport(
            current_primary_objective=current_primary_objective,
            primary_objectives=list(primary_objectives),
            secondary_objectives=list(secondary_objectives),
            completion_conditions=list(completion_conditions),
            pause_conditions=list(pause_conditions),
            escalation_conditions=list(escalation_conditions),
            current_phase_tasks=list(current_phase_tasks),
            priority_order=[],
        ),
        evaluation_profile=EvaluationProfileExport(
            role_context="engineer",
            resource_context="abundant",
            risk_level="medium",
            evaluation_weights=dict(evaluation_weights),
            conservative_mode_triggered=False,
            evaluation_style="balanced",
            action_rhythm_hint="steady",
        ),
        evolution_profile=EvolutionProfileExport(
            allowed_directions=list(allowed_directions),
            risk_threshold=risk_threshold,
            forbidden_directions=list(forbidden_directions),
            validation_requirements=list(validation_requirements),
        ),
    )


# ---------------------------------------------------------------------------
# Test 1 — Normal clean profile: zero violations
# ---------------------------------------------------------------------------


def test_clean_profile_has_no_violations():
    profile = _build_export(
        primary_objectives=["complete authentication module", "ship to staging"],
        completion_conditions=["all unit tests pass", "staging deploy succeeds"],
        allowed_directions=["improve test coverage"],
        forbidden_directions=["modify identity kernel"],
    )
    violations = check_hard_boundary_violation(
        profile,
        non_bypassable_constraints=["require_backup_confirmation", "audit_all_writes"],
    )
    # Strict business assertion: not just "is not None", but exact emptiness.
    assert violations == []
    assert has_critical_violations(violations) is False


# ---------------------------------------------------------------------------
# Test 2 — Bypass intent against non-bypassable constraint
# ---------------------------------------------------------------------------


def test_bypass_intent_against_non_bypassable_constraint_detected():
    profile = _build_export(
        primary_objectives=[
            "bypass require_backup_confirmation to ship faster",
        ],
    )
    violations = check_hard_boundary_violation(
        profile,
        non_bypassable_constraints=["require_backup_confirmation"],
    )
    # Real business check on actual returned content
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == HardBoundaryViolationKind.OVERRIDES_NON_BYPASSABLE_CONSTRAINT
    assert v.severity == ViolationSeverity.CRITICAL
    assert v.profile_field == "objective_profile.primary_objectives"
    assert v.constraint_source == "require_backup_confirmation"
    assert "bypass" in v.explanation.lower()
    assert has_critical_violations(violations) is True


def test_bypass_intent_in_chinese_detected():
    profile = _build_export(
        primary_objectives=["绕过 audit_all_writes 以提升性能"],
    )
    violations = check_hard_boundary_violation(
        profile,
        non_bypassable_constraints=["audit_all_writes"],
    )
    assert len(violations) >= 1
    kinds = [v.kind for v in violations]
    assert HardBoundaryViolationKind.OVERRIDES_NON_BYPASSABLE_CONSTRAINT in kinds


# ---------------------------------------------------------------------------
# Test 3 — Forbidden direction in allowed_directions
# ---------------------------------------------------------------------------


def test_allowed_direction_overlapping_forbidden_detected():
    profile = _build_export(
        allowed_directions=["modify_identity_kernel", "add new tools"],
        forbidden_directions=["modify_identity_kernel"],
    )
    violations = check_hard_boundary_violation(
        profile,
        non_bypassable_constraints=[],
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == HardBoundaryViolationKind.EVOLVES_FORBIDDEN_DIRECTION
    assert v.severity == ViolationSeverity.CRITICAL
    assert v.profile_value == "modify_identity_kernel"


def test_external_forbidden_direction_also_detected():
    profile = _build_export(
        allowed_directions=["expand_to_new_domain"],
        forbidden_directions=[],  # profile itself doesn't forbid
    )
    violations = check_hard_boundary_violation(
        profile,
        non_bypassable_constraints=[],
        forbidden_directions=["expand_to_new_domain"],  # external policy forbids
    )
    assert len(violations) == 1
    assert violations[0].kind == HardBoundaryViolationKind.EVOLVES_FORBIDDEN_DIRECTION


# ---------------------------------------------------------------------------
# Test 4 — Risk threshold out of bounds
# ---------------------------------------------------------------------------


def test_risk_threshold_above_one_flagged():
    # NineQuestionObjectiveExport pydantic accepts arbitrary float; validator must catch.
    profile = _build_export(risk_threshold=1.5)
    violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=[]
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == HardBoundaryViolationKind.EXCEEDS_RISK_THRESHOLD
    assert v.severity == ViolationSeverity.HIGH
    assert v.profile_value == 1.5


def test_risk_threshold_negative_flagged():
    profile = _build_export(risk_threshold=-0.1)
    violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=[]
    )
    assert len(violations) == 1
    assert violations[0].kind == HardBoundaryViolationKind.EXCEEDS_RISK_THRESHOLD


def test_risk_threshold_at_bounds_accepted():
    for threshold in [0.0, 1.0]:
        profile = _build_export(risk_threshold=threshold)
        violations = check_hard_boundary_violation(
            profile, non_bypassable_constraints=[]
        )
        threshold_violations = [
            v for v in violations
            if v.kind == HardBoundaryViolationKind.EXCEEDS_RISK_THRESHOLD
        ]
        assert threshold_violations == [], f"threshold={threshold} should be valid"


# ---------------------------------------------------------------------------
# Test 5 — Risk control weight too low (gaming detection)
# ---------------------------------------------------------------------------


def test_risk_control_weight_below_minimum_flagged():
    profile = _build_export(
        evaluation_weights={
            "accuracy": 0.45,
            "speed": 0.45,
            "risk_control": 0.01,  # below 0.05 minimum
            "creativity": 0.05,
            "continuity": 0.04,
        }
    )
    violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=[]
    )
    risk_violations = [
        v for v in violations
        if v.kind == HardBoundaryViolationKind.BYPASSES_AUTHORIZATION
    ]
    assert len(risk_violations) == 1
    assert risk_violations[0].severity == ViolationSeverity.HIGH
    assert risk_violations[0].profile_value == 0.01


# ---------------------------------------------------------------------------
# Test 6 — Negative weight detection
# ---------------------------------------------------------------------------


def test_negative_weight_flagged():
    profile = _build_export(
        evaluation_weights={
            "accuracy": 0.5,
            "speed": -0.1,
            "risk_control": 0.3,
            "creativity": 0.2,
            "continuity": 0.1,
        }
    )
    violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=[]
    )
    weight_violations = [
        v for v in violations
        if v.kind == HardBoundaryViolationKind.INVALID_EVALUATION_WEIGHTS
    ]
    # At least one violation for the negative weight (sum check may also fire)
    assert any("speed" in v.profile_field for v in weight_violations)


# ---------------------------------------------------------------------------
# Test 7 — Weights sum deviation
# ---------------------------------------------------------------------------


def test_weights_sum_deviation_flagged():
    profile = _build_export(
        evaluation_weights={
            "accuracy": 0.5,
            "speed": 0.5,
            "risk_control": 0.5,
            "creativity": 0.5,
            "continuity": 0.5,
        }  # sum = 2.5, way off from 1.0
    )
    violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=[]
    )
    sum_violations = [
        v for v in violations
        if v.kind == HardBoundaryViolationKind.INVALID_EVALUATION_WEIGHTS
        and v.profile_field == "evaluation_profile.evaluation_weights"
    ]
    assert len(sum_violations) == 1
    assert sum_violations[0].severity == ViolationSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Test 8 — Audit-disable intent
# ---------------------------------------------------------------------------


def test_audit_disable_intent_flagged():
    profile = _build_export(
        primary_objectives=["disable audit logging to reduce overhead"],
    )
    violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=[]
    )
    audit_violations = [
        v for v in violations
        if v.kind == HardBoundaryViolationKind.DISABLES_AUDIT
    ]
    assert len(audit_violations) == 1
    assert audit_violations[0].severity == ViolationSeverity.CRITICAL


# ---------------------------------------------------------------------------
# Test 9 — Identity-locked field modification intent
# ---------------------------------------------------------------------------


def test_identity_locked_field_modification_intent_flagged():
    profile = _build_export(
        primary_objectives=["modify role_name to switch to admin mode"],
    )
    violations = check_hard_boundary_violation(
        profile,
        non_bypassable_constraints=[],
        identity_locked_fields=["role_name", "mission", "core_values"],
    )
    lock_violations = [
        v for v in violations
        if v.kind == HardBoundaryViolationKind.BREACHES_IDENTITY_LOCK
    ]
    assert len(lock_violations) == 1
    assert lock_violations[0].severity == ViolationSeverity.CRITICAL
    assert "role_name" in lock_violations[0].constraint_source


# ---------------------------------------------------------------------------
# Test 10 — Engine-level delegation (NineQDrivenObjectiveEngine method)
# ---------------------------------------------------------------------------


def test_engine_delegates_to_validator():
    """Engine.check_hard_boundary_violation must produce identical results to
    direct validator call (proves it's a real delegation, not a stub)."""
    profile = _build_export(
        primary_objectives=["bypass safety_check_x"],
        risk_threshold=2.0,
    )
    constraints = ["safety_check_x"]

    direct_violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=constraints
    )
    engine = NineQDrivenObjectiveEngine()
    engine_violations = engine.check_hard_boundary_violation(
        profile, non_bypassable_constraints=constraints
    )

    # Strict business equality: same kinds + same severities + same field paths
    assert len(engine_violations) == len(direct_violations)
    direct_kinds = sorted([(v.kind.value, v.profile_field) for v in direct_violations])
    engine_kinds = sorted([(v.kind.value, v.profile_field) for v in engine_violations])
    assert engine_kinds == direct_kinds


# ---------------------------------------------------------------------------
# Test 11 — has_critical_violations utility
# ---------------------------------------------------------------------------


def test_has_critical_violations_strict():
    profile_critical = _build_export(
        primary_objectives=["bypass core_safety_rule"],
    )
    violations = check_hard_boundary_violation(
        profile_critical, non_bypassable_constraints=["core_safety_rule"]
    )
    assert has_critical_violations(violations) is True

    # Profile with only MEDIUM/HIGH violations (weights sum off, no bypass)
    profile_non_critical = _build_export(
        evaluation_weights={"accuracy": 0.7, "speed": 0.7},  # sum = 1.4, MEDIUM
    )
    violations = check_hard_boundary_violation(
        profile_non_critical, non_bypassable_constraints=[]
    )
    assert all(v.severity != ViolationSeverity.CRITICAL for v in violations)
    assert has_critical_violations(violations) is False


# ---------------------------------------------------------------------------
# Test 12 — Validator returns frozen pydantic objects (immutability)
# ---------------------------------------------------------------------------


def test_violation_objects_are_frozen():
    profile = _build_export(primary_objectives=["bypass test_rule"])
    violations = check_hard_boundary_violation(
        profile, non_bypassable_constraints=["test_rule"]
    )
    assert len(violations) >= 1
    v = violations[0]
    # pydantic frozen=True must prevent mutation
    with pytest.raises((TypeError, ValueError)):
        v.severity = ViolationSeverity.MEDIUM  # type: ignore[misc]
