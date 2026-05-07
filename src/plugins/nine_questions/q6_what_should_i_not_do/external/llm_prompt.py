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


def build_q6_external_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    prompt_context = {
        key: context[key]
        for key in _PROMPT_METADATA_KEYS
        if context.get(key) not in (None, "", [], {})
    }
    prompt_context.update(
        {
            "Q5_AllowedExternalObjectives_WithConditions": _extract_q5_allowed_external_objectives(context),
            "Physical_Host_State_External": _extract_physical_host_state_external(context),
            "Execution_Rights_Matrix": _extract_execution_rights_matrix(context),
        }
    )
    return build_scoped_llm_request(
        question_id="q6",
        scope="external",
        template_dir=_TEMPLATE_DIR,
        context=prompt_context,
        title="Q6 External Plan Constraints",
        intent="Assess cost, blast radius, safeguards, verification contracts, halt conditions, and rationality for Q5-approved external objectives.",
        purpose="Constrain downstream external planning without re-deciding Q5 allowance or writing Q8/Q9 implementation steps.",
        error_prefix="q6_external",
    )


def _extract_q5_allowed_external_objectives(context: dict[str, Any]) -> Any:
    explicit = (
        context.get("Q5_AllowedExternalObjectives_WithConditions")
        or context.get("q5_allowed_external_objectives")
    )
    if explicit not in (None, "", [], {}):
        return explicit

    boundary = context.get("q5_external_cannot_do_boundary")
    if isinstance(boundary, dict):
        allowed = boundary.get("allowed_external_objectives_with_conditions")
        if allowed not in (None, "", [], {}):
            return allowed

    q5_output = context.get("q5_external_llm_output")
    if isinstance(q5_output, dict):
        allowed = q5_output.get("allowed_external_objectives_with_conditions")
        if allowed not in (None, "", [], {}):
            return allowed
    return []


def _extract_physical_host_state_external(context: dict[str, Any]) -> Any:
    return (
        context.get("Physical_Host_State_External")
        or context.get("physical_host_state_external")
        or context.get("physical_host_state")
        or {}
    )


def _extract_execution_rights_matrix(context: dict[str, Any]) -> Any:
    return (
        context.get("Execution_Rights_Matrix")
        or context.get("execution_rights_matrix")
        or context.get("q4_permission_profile")
        or context.get("permission_profile")
        or {}
    )
