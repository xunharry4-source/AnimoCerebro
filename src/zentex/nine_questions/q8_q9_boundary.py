from __future__ import annotations

import re
from typing import Any


Q8_OWNED_OUTPUT_FIELDS = frozenset({"objective_profile", "task_queue"})
Q9_OWNED_OUTPUT_FIELDS = frozenset(
    {
        "current_action_plan",
        "method_selection",
        "required_resources",
        "assigned_role_profile",
        "risk_assessment",
        "on_failure_action",
        "estimated_confidence",
        "expected_results",
        "candidate_alternatives",
        "nine_question_mapping",
    }
)
Q9_LEGACY_POSTURE_FIELDS = frozenset({"evaluation_profile", "evolution_profile", "escalation_profile"})


class NineQuestionBoundaryError(RuntimeError):
    def __init__(self, *, question_id: str, forbidden_fields: list[str]) -> None:
        self.question_id = question_id
        self.forbidden_fields = forbidden_fields
        super().__init__(
            f"{question_id} output crossed question boundary: {', '.join(forbidden_fields)}"
        )


class GoalInheritanceError(RuntimeError):
    def __init__(
        self,
        *,
        source_question: str,
        target_question: str,
        expected_goal: str,
        actual_goal: str,
    ) -> None:
        self.source_question = source_question
        self.target_question = target_question
        self.expected_goal = expected_goal
        self.actual_goal = actual_goal
        super().__init__(
            f"{target_question} goal drift from {source_question}: "
            f"expected inherited goal={expected_goal!r}; actual goal={actual_goal!r}"
        )


_GOAL_FIELD_PRIORITY = (
    "final_intervention_goal",
    "intent_objective",
    "task_goal",
    "goal",
    "objective",
    "plan_objective",
    "current_mission",
    "intent",
    "description",
    "intent_description",
    "title",
    "intent_name",
)
_GOAL_TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _present_fields(payload: Any, fields: frozenset[str]) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return sorted(field for field in fields if field in payload)


def extract_goal_text(payload: Any) -> str:
    if isinstance(payload, dict):
        for field in _GOAL_FIELD_PRIORITY:
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return str(value)
        for value in payload.values():
            if isinstance(value, dict):
                nested = extract_goal_text(value)
                if nested:
                    return nested
    if isinstance(payload, str):
        return payload.strip()
    return ""


def normalize_goal_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(_GOAL_TOKEN_PATTERN.findall(text))


def validate_goal_inheritance(
    *,
    source_question: str,
    target_question: str,
    expected_goal: Any,
    actual_goal: Any,
) -> None:
    expected = extract_goal_text(expected_goal)
    actual = extract_goal_text(actual_goal)
    normalized_expected = normalize_goal_text(expected)
    normalized_actual = normalize_goal_text(actual)
    if not normalized_expected:
        raise GoalInheritanceError(
            source_question=source_question,
            target_question=target_question,
            expected_goal="",
            actual_goal=actual,
        )
    if not normalized_actual or normalized_expected not in normalized_actual:
        raise GoalInheritanceError(
            source_question=source_question,
            target_question=target_question,
            expected_goal=expected,
            actual_goal=actual,
        )


def validate_q8_output_boundary(payload: Any) -> None:
    forbidden = _present_fields(payload, Q9_OWNED_OUTPUT_FIELDS)
    if forbidden:
        raise NineQuestionBoundaryError(question_id="q8", forbidden_fields=forbidden)


def validate_q9_output_boundary(payload: Any) -> None:
    forbidden = _present_fields(payload, Q8_OWNED_OUTPUT_FIELDS | Q9_LEGACY_POSTURE_FIELDS)
    if forbidden:
        raise NineQuestionBoundaryError(question_id="q9", forbidden_fields=forbidden)
