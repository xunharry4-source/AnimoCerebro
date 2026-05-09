from __future__ import annotations

from typing import Any

from zentex.nine_questions.objective_engine import NineQDrivenObjectiveEngine


OBJECTIVE_CONTEXT_PHASES = frozenset({"frame", "decision_synthesis"})


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_snapshot_map(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    explicit = _as_dict(
        context.get("nine_question_snapshot_map")
        or context.get("question_snapshots")
    )
    if explicit:
        return {str(key): snapshot for key, snapshot in explicit.items() if isinstance(snapshot, dict)}

    nine_question_state = _as_dict(context.get("nine_question_state"))
    snapshots = _as_dict(nine_question_state.get("question_snapshots"))
    return {str(key): snapshot for key, snapshot in snapshots.items() if isinstance(snapshot, dict)}


def build_think_loop_objective_context(
    *,
    context: dict[str, Any],
    phase_name: str,
) -> dict[str, Any]:
    if phase_name not in OBJECTIVE_CONTEXT_PHASES:
        return {}

    snapshot_map = _extract_snapshot_map(context)
    if not snapshot_map:
        return {
            "nine_question_objective_context": {
                "profile_status": "missing",
                "target_phase": phase_name,
                "missing_sources": ["nine_question_state.question_snapshots"],
            }
        }

    if "q8" not in snapshot_map and "q9" not in snapshot_map:
        return {
            "nine_question_objective_context": {
                "profile_status": "missing",
                "target_phase": phase_name,
                "missing_sources": ["q8.snapshot", "q9.snapshot"],
            }
        }

    export = NineQDrivenObjectiveEngine().derive_profiles(snapshot_map)
    export_payload = export.model_dump(mode="json")
    return {
        "nine_question_objective_context": {
            "profile_status": "ready",
            "target_phase": phase_name,
            "source_question_ids": export_payload["source_question_ids"],
            "source_trace_ids": export_payload["source_trace_ids"],
            "objective_profile": export_payload["objective_profile"],
            "evaluation_profile": export_payload["evaluation_profile"],
            "evolution_profile": export_payload["evolution_profile"],
            "escalation_profile": export_payload["escalation_profile"],
            "derivation_trace": export_payload["derivation_trace"],
        }
    }


def enrich_context_for_objective_phase(
    *,
    context: dict[str, Any],
    phase_name: str,
) -> dict[str, Any]:
    objective_context = build_think_loop_objective_context(context=context, phase_name=phase_name)
    if not objective_context:
        return dict(context)
    return {
        **context,
        **objective_context,
    }
