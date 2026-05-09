from __future__ import annotations

from typing import Any

from zentex.common.workflow_models import EvolutionEvidence


def _walk(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for item in value.values():
            values.extend(_walk(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_walk(item))
    return values


def _contains_marker(value: Any, marker: str) -> bool:
    if not marker:
        return False
    needle = marker.lower()
    return any(needle in str(item).lower() for item in _walk(value))


def verify_turn_to_turn_evolution(
    *,
    previous_trace_id: str,
    current_trace_id: str,
    session_id: str,
    current_snapshots: dict[str, Any],
    expected_learning_markers: list[str] | None = None,
    expected_memory_markers: list[str] | None = None,
    expected_reflection_markers: list[str] | None = None,
    task_id: str = "",
) -> dict[str, Any]:
    expected_learning_markers = list(expected_learning_markers or [])
    expected_memory_markers = list(expected_memory_markers or [])
    expected_reflection_markers = list(expected_reflection_markers or [])

    memory_ok = bool(expected_memory_markers) and all(_contains_marker(current_snapshots, item) for item in expected_memory_markers)
    learning_ok = bool(expected_learning_markers) and all(_contains_marker(current_snapshots, item) for item in expected_learning_markers)
    reflection_ok = bool(expected_reflection_markers) and all(_contains_marker(current_snapshots, item) for item in expected_reflection_markers)
    strategy_ok = any(
        _contains_marker(current_snapshots, marker)
        for marker in ("strategy_self_optimized", "agent_logic_evolved", "cautious", "confirm_before_commit")
    )

    failures = []
    if expected_memory_markers and not memory_ok:
        failures.append({"reason": "memory_not_applied", "error_code": "EVOLUTION_LINK_MISSING", "markers": expected_memory_markers})
    if expected_learning_markers and not learning_ok:
        failures.append({"reason": "learning_not_applied", "error_code": "EVOLUTION_LINK_MISSING", "markers": expected_learning_markers})
    if expected_reflection_markers and not reflection_ok:
        failures.append({"reason": "reflection_not_applied", "error_code": "EVOLUTION_LINK_MISSING", "markers": expected_reflection_markers})
    if not any((memory_ok, learning_ok, reflection_ok, strategy_ok)):
        failures.append(
            {
                "reason": "turn_to_turn_evolution_missing",
                "error_code": "EVOLUTION_LINK_MISSING",
                "previous_trace_id": previous_trace_id,
                "current_trace_id": current_trace_id,
            }
        )

    status = "succeeded" if not failures else "failed"
    return EvolutionEvidence(
        status=status,
        error_code="" if status == "succeeded" else "EVOLUTION_LINK_MISSING",
        trace_id=current_trace_id,
        session_id=session_id,
        task_id=task_id,
        node_id="evolution",
        node_name="Turn To Turn Evolution",
        evidence_ref=f"evolution:{previous_trace_id}->{current_trace_id}",
        evidence={
            "previous_trace_id": previous_trace_id,
            "current_trace_id": current_trace_id,
            "expected_learning_markers": expected_learning_markers,
            "expected_memory_markers": expected_memory_markers,
            "expected_reflection_markers": expected_reflection_markers,
        },
        failures=failures,
        proactive_memory_retrieval_success=memory_ok,
        learning_applied_to_action_candidates=learning_ok,
        reflection_applied_to_posture=reflection_ok,
        strategy_self_optimized=strategy_ok,
    ).as_dict()
