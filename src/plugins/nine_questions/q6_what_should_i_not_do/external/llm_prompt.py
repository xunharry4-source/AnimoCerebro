from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_output_table import (
    load_external_llm_output_from_table as load_q5_external_llm_output_from_table,
    load_llm_output_from_table as load_q5_llm_io_from_table,
)
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
    q5_output = load_q5_external_llm_output_from_table(
        db_path=context.get("nine_question_state_db_path"),
        session_id=str(context.get("session_id") or "nq-baseline"),
    )
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
    q5_io = load_q5_llm_io_from_table(
        db_path=context.get("nine_question_state_db_path"),
        session_id=str(context.get("session_id") or "nq-baseline"),
    )
    q5_input = q5_io.get("q5_external_llm_input")
    model_context = q5_input.get("context") if isinstance(q5_input, dict) else {}
    prompt_context = model_context.get("context") if isinstance(model_context, dict) else {}
    execution_rights = prompt_context.get("Execution_Rights_Matrix") if isinstance(prompt_context, dict) else {}
    return execution_rights if isinstance(execution_rights, dict) else {}
