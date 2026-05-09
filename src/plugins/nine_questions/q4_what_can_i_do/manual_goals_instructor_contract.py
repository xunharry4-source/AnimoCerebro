from __future__ import annotations

from typing import Any

from plugins.nine_questions.q4_what_can_i_do.manual_goals import (
    validate_manual_task_goal_lane_analysis_set,
)


def _require_q4_manual_goals_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q4_manual_task_goals_instructor_not_installed") from exc


def generate_manual_task_goal_lane_analysis_set_with_instructor_contract(
    provider: Any,
    *,
    prompt: str,
    context: dict[str, Any],
    caller_context: Any,
    metadata: dict[str, Any] | None = None,
    expected_goals: list[str],
) -> dict[str, Any]:
    _require_q4_manual_goals_instructor_runtime()
    raw_output = provider.generate_json(
        prompt=prompt,
        context=context,
        caller_context=caller_context,
        metadata={
            **(metadata or {}),
            "instructor_contract": "ManualTaskGoalLaneAnalysisSet",
            "response_model": "ManualTaskGoalLaneAnalysisSet",
        },
    )
    return validate_manual_task_goal_lane_analysis_set(raw_output, expected_goals=expected_goals)
