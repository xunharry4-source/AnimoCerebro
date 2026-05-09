from __future__ import annotations

from typing import Any

from plugins.nine_questions.q4_what_can_i_do.semantic_guard import (
    Q4ObjectiveLane,
    validate_q4_objective_semantic_guard_result,
)


def _require_q4_semantic_guard_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q4_semantic_guard_instructor_not_installed") from exc


def generate_q4_objective_semantic_guard_result_with_instructor_contract(
    provider: Any,
    *,
    prompt: str,
    context: dict[str, Any],
    caller_context: Any,
    metadata: dict[str, Any] | None = None,
    lane: Q4ObjectiveLane,
    candidate_set: dict[str, Any],
) -> dict[str, Any]:
    _require_q4_semantic_guard_instructor_runtime()
    raw_output = provider.generate_json(
        prompt=prompt,
        context=context,
        caller_context=caller_context,
        metadata={
            **(metadata or {}),
            "instructor_contract": "Q4ObjectiveSemanticGuardResult",
            "response_model": "Q4ObjectiveSemanticGuardResult",
        },
    )
    return validate_q4_objective_semantic_guard_result(
        raw_output,
        lane=lane,
        candidate_set=candidate_set,
    )
