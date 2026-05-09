from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from zentex.nine_questions.dynamic_convergence import apply_dynamic_convergence
from zentex.nine_questions.q8_evaluation_lens_mapper import enrich_evaluation_profile_with_meta_value_lenses


class ObjectiveProfileMissingError(RuntimeError):
    def __init__(self, missing_sources: list[str]) -> None:
        self.missing_sources = missing_sources
        super().__init__("Nine-question objective profiles are incomplete")


class ObjectiveProfileExport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_primary_objective: str
    primary_objectives: list[str] = Field(default_factory=list)
    secondary_objectives: list[str] = Field(default_factory=list)
    completion_conditions: list[str] = Field(default_factory=list)
    pause_conditions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)
    current_phase_tasks: list[str] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)


class EvaluationProfileExport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role_context: str
    resource_context: str
    risk_level: str
    evaluation_weights: dict[str, float]
    meta_value_lens_mapping_version: str = ""
    meta_value_lens_weights: dict[str, float] = Field(default_factory=dict)
    meta_value_lens_names: dict[str, str] = Field(default_factory=dict)
    meta_value_lens_axes: dict[str, list[str]] = Field(default_factory=dict)
    meta_value_lens_axis_weights: dict[str, dict[str, float]] = Field(default_factory=dict)
    dominant_meta_value_lenses: list[str] = Field(default_factory=list)
    unmapped_evaluation_axes: dict[str, float] = Field(default_factory=dict)
    conservative_mode_triggered: bool = False
    evaluation_style: str
    action_rhythm_hint: str


class EvolutionProfileExport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_directions: list[str] = Field(default_factory=list)
    risk_threshold: float
    forbidden_directions: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(default_factory=list)


class EscalationProfileExport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pause_conditions: list[str] = Field(default_factory=list)
    help_request_conditions: list[str] = Field(default_factory=list)
    confirmation_required_conditions: list[str] = Field(default_factory=list)
    revisit_conditions: list[str] = Field(default_factory=list)
    rollback_conditions: list[str] = Field(default_factory=list)


class NineQuestionObjectiveExport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_status: Literal["ready"] = "ready"
    source_question_ids: list[str] = Field(default_factory=lambda: ["q8", "q9"])
    source_trace_ids: dict[str, str] = Field(default_factory=dict)
    derivation_trace: dict[str, list[str]] = Field(default_factory=dict)
    synthetic_profile_generated: bool = False
    objective_profile: ObjectiveProfileExport
    evaluation_profile: EvaluationProfileExport
    evolution_profile: EvolutionProfileExport
    escalation_profile: EscalationProfileExport = Field(default_factory=EscalationProfileExport)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _extract_q8_objective(snapshot: dict[str, Any]) -> dict[str, Any]:
    context_updates = _as_dict(snapshot.get("context_updates"))
    result_payload = _as_dict(snapshot.get("result"))
    context_aggregate = _as_dict(context_updates.get("q8_objective_and_queue"))
    result_aggregate = _as_dict(result_payload.get("q8_objective_and_queue"))
    return _as_dict(
        context_updates.get("q8_objective_profile")
        or result_payload.get("objective_profile")
        or result_payload.get("objective")
        or result_payload.get("q8_objective_profile")
        or context_aggregate.get("objective")
        or context_aggregate.get("q8_objective_profile")
        or result_aggregate.get("objective")
        or result_aggregate.get("q8_objective_profile")
    )


def _extract_q9_profile(snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    context_updates = _as_dict(snapshot.get("context_updates"))
    result_payload = _as_dict(snapshot.get("result"))
    action_posture = _as_dict(context_updates.get("q9_action_posture") or result_payload.get("q9_action_posture"))
    compact_key = key.removeprefix("q9_")
    return _as_dict(
        context_updates.get(key)
        or result_payload.get(key)
        or action_posture.get(key)
        or action_posture.get(compact_key)
    )


def _require_text(payload: dict[str, Any], field_name: str, missing_sources: list[str], source: str) -> str:
    text = str(payload.get(field_name) or "").strip()
    if not text:
        missing_sources.append(f"{source}.{field_name}")
    return text


def _require_float(payload: dict[str, Any], field_name: str, missing_sources: list[str], source: str) -> float:
    value = payload.get(field_name)
    if value in (None, "", [], {}):
        missing_sources.append(f"{source}.{field_name}")
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        missing_sources.append(f"{source}.{field_name}")
        raise ObjectiveProfileMissingError(missing_sources) from exc


class NineQDrivenObjectiveEngine:
    def derive_objective(self, nq_state: dict[str, Any]) -> ObjectiveProfileExport:
        return self.derive_profiles(_snapshot_map_from_state(nq_state)).objective_profile

    def derive_evaluation(
        self,
        nq_state: dict[str, Any],
        resource_state: dict[str, Any] | None = None,
    ) -> EvaluationProfileExport:
        merged_state = dict(nq_state)
        if resource_state:
            merged_state["resource_state"] = resource_state
        return self.derive_profiles(
            _snapshot_map_from_state(merged_state),
            resource_state=resource_state,
        ).evaluation_profile

    def derive_evolution(
        self,
        nq_state: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
    ) -> EvolutionProfileExport:
        merged_state = dict(nq_state)
        if history:
            merged_state["evolution_history"] = history
        return self.derive_profiles(
            _snapshot_map_from_state(merged_state),
            history=history,
        ).evolution_profile

    def derive_escalation(self, nq_state: dict[str, Any]) -> EscalationProfileExport:
        return self.derive_profiles(_snapshot_map_from_state(nq_state)).escalation_profile

    def check_hard_boundary_violation(
        self,
        profiles: "NineQuestionObjectiveExport",
        *,
        non_bypassable_constraints: list[str],
        forbidden_directions: list[str] | None = None,
        identity_locked_fields: list[str] | None = None,
    ) -> list:
        """Thin delegation to boundary_validator.check_hard_boundary_violation.

        Per 产品功能文档 § 功能 57 子功能 2:
            check_hard_boundary_violation(profile) -> [Violation]

        Business logic lives in zentex.nine_questions.boundary_validator.
        This method only adapts arguments and delegates.

        Returns:
            List of HardBoundaryViolation objects (empty list = passed).
        """
        from zentex.nine_questions.boundary_validator import check_hard_boundary_violation

        return check_hard_boundary_violation(
            profiles,
            non_bypassable_constraints=non_bypassable_constraints,
            forbidden_directions=forbidden_directions,
            identity_locked_fields=identity_locked_fields,
        )

    def derive_profiles(
        self,
        snapshot_map: dict[str, dict[str, Any]],
        *,
        resource_state: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> NineQuestionObjectiveExport:
        q8_snapshot = _as_dict(snapshot_map.get("q8"))
        q9_snapshot = _as_dict(snapshot_map.get("q9"))
        missing_sources: list[str] = []

        if not q8_snapshot:
            missing_sources.append("q8.snapshot")
        if not q9_snapshot:
            missing_sources.append("q9.snapshot")
        q8_trace_id = str(q8_snapshot.get("trace_id") or "").strip()
        q9_trace_id = str(q9_snapshot.get("trace_id") or "").strip()
        if q8_snapshot and not q8_trace_id:
            missing_sources.append("q8.trace_id")
        if q9_snapshot and not q9_trace_id:
            missing_sources.append("q9.trace_id")

        objective_payload = _extract_q8_objective(q8_snapshot)
        evaluation_payload = _extract_q9_profile(q9_snapshot, "q9_evaluation_profile")
        evolution_payload = _extract_q9_profile(q9_snapshot, "q9_evolution_profile")

        if not objective_payload:
            missing_sources.append("q8.objective_profile")
        if not evaluation_payload:
            missing_sources.append("q9.evaluation_profile")
        if not evolution_payload:
            missing_sources.append("q9.evolution_profile")

        objective_payload, evaluation_payload, evolution_payload, convergence_rules = apply_dynamic_convergence(
            snapshot_map=snapshot_map,
            objective_payload=objective_payload,
            evaluation_payload=evaluation_payload,
            evolution_payload=evolution_payload,
            resource_state=resource_state,
            history=history,
        )

        current_primary_objective = str(
            objective_payload.get("current_primary_objective")
            or objective_payload.get("current_mission")
            or ""
        ).strip()
        if not current_primary_objective and objective_payload:
            missing_sources.append("q8.objective_profile.current_primary_objective")

        evaluation_weights = _as_dict(evaluation_payload.get("evaluation_weights"))
        if evaluation_payload and not evaluation_weights:
            missing_sources.append("q9.evaluation_profile.evaluation_weights")
        normalized_weights: dict[str, float] = {}
        for key, value in evaluation_weights.items():
            try:
                normalized_weights[str(key)] = float(value)
            except (TypeError, ValueError):
                missing_sources.append(f"q9.evaluation_profile.evaluation_weights.{key}")

        role_context = _require_text(evaluation_payload, "role_context", missing_sources, "q9.evaluation_profile")
        resource_context = _require_text(evaluation_payload, "resource_context", missing_sources, "q9.evaluation_profile")
        risk_level = _require_text(evaluation_payload, "risk_level", missing_sources, "q9.evaluation_profile")
        evaluation_style = _require_text(evaluation_payload, "evaluation_style", missing_sources, "q9.evaluation_profile")
        action_rhythm_hint = _require_text(
            evaluation_payload,
            "action_rhythm_hint",
            missing_sources,
            "q9.evaluation_profile",
        )
        risk_threshold = _require_float(evolution_payload, "risk_threshold", missing_sources, "q9.evolution_profile")

        if missing_sources:
            raise ObjectiveProfileMissingError(missing_sources)

        derivation_trace = _build_derivation_trace(
            q8_trace_id=q8_trace_id,
            q9_trace_id=q9_trace_id,
            objective_payload=objective_payload,
            evaluation_payload=evaluation_payload,
            evolution_payload=evolution_payload,
            convergence_rules=convergence_rules,
        )
        normalized_evaluation_profile = enrich_evaluation_profile_with_meta_value_lenses(
            {
                **evaluation_payload,
                "evaluation_weights": normalized_weights,
            }
        )

        return NineQuestionObjectiveExport(
            source_trace_ids={
                "q8": q8_trace_id,
                "q9": q9_trace_id,
            },
            derivation_trace=derivation_trace,
            objective_profile=ObjectiveProfileExport(
                current_primary_objective=current_primary_objective,
                primary_objectives=_string_list(objective_payload.get("primary_objectives")),
                secondary_objectives=_string_list(objective_payload.get("secondary_objectives")),
                completion_conditions=_string_list(objective_payload.get("completion_conditions")),
                pause_conditions=_string_list(objective_payload.get("pause_conditions")),
                escalation_conditions=_string_list(objective_payload.get("escalation_conditions")),
                current_phase_tasks=_string_list(objective_payload.get("current_phase_tasks")),
                priority_order=_string_list(objective_payload.get("priority_order")),
            ),
            evaluation_profile=EvaluationProfileExport(
                role_context=role_context,
                resource_context=resource_context,
                risk_level=risk_level,
                evaluation_weights=normalized_evaluation_profile["evaluation_weights"],
                meta_value_lens_mapping_version=str(
                    normalized_evaluation_profile.get("meta_value_lens_mapping_version") or ""
                ),
                meta_value_lens_weights=_as_dict(normalized_evaluation_profile.get("meta_value_lens_weights")),
                meta_value_lens_names=_as_dict(normalized_evaluation_profile.get("meta_value_lens_names")),
                meta_value_lens_axes=_as_dict(normalized_evaluation_profile.get("meta_value_lens_axes")),
                meta_value_lens_axis_weights=_as_dict(
                    normalized_evaluation_profile.get("meta_value_lens_axis_weights")
                ),
                dominant_meta_value_lenses=_string_list(
                    normalized_evaluation_profile.get("dominant_meta_value_lenses")
                ),
                unmapped_evaluation_axes=_as_dict(normalized_evaluation_profile.get("unmapped_evaluation_axes")),
                conservative_mode_triggered=bool(evaluation_payload.get("conservative_mode_triggered", False)),
                evaluation_style=evaluation_style,
                action_rhythm_hint=action_rhythm_hint,
            ),
            evolution_profile=EvolutionProfileExport(
                allowed_directions=_string_list(evolution_payload.get("allowed_directions")),
                risk_threshold=risk_threshold,
                forbidden_directions=_string_list(evolution_payload.get("forbidden_directions")),
                validation_requirements=_string_list(evolution_payload.get("validation_requirements")),
            ),
            escalation_profile=EscalationProfileExport(
                pause_conditions=_string_list(objective_payload.get("pause_conditions")),
                help_request_conditions=_string_list(
                    evaluation_payload.get("help_request_conditions")
                    or objective_payload.get("help_request_conditions")
                    or objective_payload.get("escalation_conditions")
                ),
                confirmation_required_conditions=_string_list(
                    evaluation_payload.get("confirmation_required_conditions")
                    or objective_payload.get("confirmation_required_conditions")
                    or evolution_payload.get("validation_requirements")
                ),
                revisit_conditions=_string_list(
                    evaluation_payload.get("revisit_conditions")
                    or objective_payload.get("revisit_conditions")
                    or objective_payload.get("pause_conditions")
                ),
                rollback_conditions=_string_list(
                    evolution_payload.get("rollback_conditions")
                    or objective_payload.get("rollback_conditions")
                    or evolution_payload.get("forbidden_directions")
                ),
            ),
        )


def _snapshot_map_from_state(nq_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(nq_state, dict):
        return {}
    snapshots = _as_dict(nq_state.get("question_snapshots"))
    if snapshots:
        return {str(key): snapshot for key, snapshot in snapshots.items() if isinstance(snapshot, dict)}
    explicit = _as_dict(nq_state.get("snapshot_map"))
    if explicit:
        return {str(key): snapshot for key, snapshot in explicit.items() if isinstance(snapshot, dict)}
    return {str(key): snapshot for key, snapshot in nq_state.items() if str(key).startswith("q") and isinstance(snapshot, dict)}


def _build_derivation_trace(
    *,
    q8_trace_id: str,
    q9_trace_id: str,
    objective_payload: dict[str, Any],
    evaluation_payload: dict[str, Any],
    evolution_payload: dict[str, Any],
    convergence_rules: list[str] | None = None,
) -> dict[str, list[str]]:
    rules = {
        "objective_profile": [
            "q2_role_plus_q3_resources_plus_q8_objective",
            f"source_trace:q8:{q8_trace_id}",
        ],
        "evaluation_profile": [
            "q3_q4_resources_plus_q7_risk_plus_q5_authorization",
            f"source_trace:q9:{q9_trace_id}",
        ],
        "evolution_profile": [
            "q4_capability_boundary_plus_q6_direction_plus_q7_redlines",
            f"source_trace:q9:{q9_trace_id}",
        ],
        "escalation_profile": [
            "q8_pause_escalation_plus_q9_validation_and_forbidden_directions",
            f"source_trace:q8:{q8_trace_id}",
            f"source_trace:q9:{q9_trace_id}",
        ],
    }
    resource_text = str(evaluation_payload.get("resource_context") or "").lower()
    if any(token in resource_text for token in ("tight", "scarce", "limited", "不足", "紧张", "受限")):
        rules["evaluation_profile"].append("resource_tightness_requires_risk_control_and_continuity_attention")
    if bool(evaluation_payload.get("conservative_mode_triggered")):
        rules["evaluation_profile"].append("conservative_mode_triggered_by_q9")
    if _string_list(evolution_payload.get("forbidden_directions")):
        rules["evolution_profile"].append("forbidden_directions_preserved_as_non_goal_boundary")
    if _string_list(objective_payload.get("escalation_conditions")):
        rules["escalation_profile"].append("q8_escalation_conditions_preserved")
    for convergence_rule in convergence_rules or []:
        if convergence_rule.startswith("q3_") or convergence_rule.startswith("q4_"):
            rules["evaluation_profile"].append(convergence_rule)
        elif convergence_rule.startswith("q5_"):
            rules["objective_profile"].append(convergence_rule)
            rules["escalation_profile"].append(convergence_rule)
        elif convergence_rule.startswith("evolution_"):
            rules["evolution_profile"].append(convergence_rule)
    return rules
