from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.nine_questions.q5_what_am_i_allowed_to_do.internal.lane_data import (
    query_q5_internal_lane_data,
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


def build_q5_internal_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    context = dict(context)
    lane_data = query_q5_internal_lane_data(context)
    prompt_context = {
        key: context[key]
        for key in _PROMPT_METADATA_KEYS
        if context.get(key) not in (None, "", [], {})
    }
    prompt_context.update(
        {
            "IdentityKernel_NonBypassableConstraints": lane_data["IdentityKernel_NonBypassableConstraints"],
            "MemoryIntegrity_And_ContinuityRules": lane_data["MemoryIntegrity_And_ContinuityRules"],
            "ProtectedModules_State": lane_data["ProtectedModules_State"],
            "Q4_InternalObjectiveCandidates": lane_data["Q4_InternalObjectiveCandidates"],
        }
    )
    return build_scoped_llm_request(
        question_id="q5",
        scope="internal",
        template_dir=_TEMPLATE_DIR,
        context=prompt_context,
        title="Q5 Internal Goal Compliance",
        intent="Derive internal cognitive safety boundaries, filter Q4 internal objectives, and attach mandatory control conditions.",
        purpose="Protect identity continuity, memory integrity, supervision, and protected modules before downstream planning.",
        error_prefix="q5_internal",
    )
