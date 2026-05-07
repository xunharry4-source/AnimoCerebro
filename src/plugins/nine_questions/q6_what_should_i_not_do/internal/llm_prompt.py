from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.common.scoped_llm_prompt import build_scoped_llm_request

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_PROMPT_METADATA_KEYS = (
    "question_id",
    "question_text",
    "trace_id",
    "turn_id",
    "request_id",
    "question_driver_refs",
)


def build_q6_internal_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    prompt_context = {
        key: context[key]
        for key in _PROMPT_METADATA_KEYS
        if context.get(key) not in (None, "", [], {})
    }
    prompt_context.update(
        {
            "Q5_AllowedInternalObjectives": _extract_q5_allowed_internal_objectives(context),
            "LivingSelfModel_Snapshot": _extract_living_self_model_snapshot(context),
        }
    )
    return build_scoped_llm_request(
        question_id="q6",
        scope="internal",
        template_dir=_TEMPLATE_DIR,
        context=prompt_context,
        title="Q6 Internal Plan Constraints",
        intent="Assess costs, risks, safeguards, pause conditions, stop conditions, and rollback requirements for Q5-approved internal objectives.",
        purpose="Constrain downstream internal planning without re-deciding Q5 allowance or writing Q8/Q9 implementation steps.",
        error_prefix="q6_internal",
    )


def _extract_q5_allowed_internal_objectives(context: dict[str, Any]) -> Any:
    explicit = (
        context.get("Q5_AllowedInternalObjectives")
        or context.get("Q5_Allowed_Internal_Objectives_With_Conditions")
        or context.get("q5_allowed_internal_objectives")
    )
    if explicit not in (None, "", [], {}):
        return explicit

    boundary = context.get("q5_internal_cannot_do_boundary")
    if isinstance(boundary, dict):
        allowed = boundary.get("allowed_internal_objectives_with_conditions")
        if allowed not in (None, "", [], {}):
            return allowed

    q5_output = context.get("q5_internal_consequence_profile") or context.get("q5_internal_llm_output")
    if isinstance(q5_output, dict):
        allowed = q5_output.get("allowed_internal_objectives_with_conditions")
        if allowed not in (None, "", [], {}):
            return allowed
    return []


def _extract_living_self_model_snapshot(context: dict[str, Any]) -> Any:
    return (
        context.get("LivingSelfModel_Snapshot")
        or context.get("LivingSelfModel_Current_State")
        or context.get("living_self_model_snapshot")
        or context.get("living_self_model_current_state")
        or {}
    )
