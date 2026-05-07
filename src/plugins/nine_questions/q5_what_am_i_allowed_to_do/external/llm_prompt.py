from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.nine_questions.q5_what_am_i_allowed_to_do.external.lane_data import (
    query_q5_external_lane_data,
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


def build_q5_external_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    context = dict(context)
    lane_data = query_q5_external_lane_data(context)
    prompt_context = {
        key: context[key]
        for key in _PROMPT_METADATA_KEYS
        if context.get(key) not in (None, "", [], {})
    }
    prompt_context.update(
        {
            "SafetyGate_Redlines_External": lane_data["SafetyGate_Redlines_External"],
            "Execution_Rights_Matrix": lane_data["Execution_Rights_Matrix"],
            "CloudAudit_Policies": lane_data["CloudAudit_Policies"],
            "Q4_ExternalObjectiveCandidates": lane_data["Q4_ExternalObjectiveCandidates"],
        }
    )
    return build_scoped_llm_request(
        question_id="q5",
        scope="external",
        template_dir=_TEMPLATE_DIR,
        context=prompt_context,
        title="Q5 External Goal Compliance",
        intent="Derive external safety boundaries, filter Q4 external objectives, and attach mandatory compliance conditions.",
        purpose="Block unsafe external side effects and gate allowed objectives before downstream planning.",
        error_prefix="q5_external",
    )
