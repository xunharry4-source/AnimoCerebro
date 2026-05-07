from __future__ import annotations

from copy import deepcopy
from typing import Any


_PROMPT_METADATA_KEYS = (
    "question_id",
    "question_text",
    "trace_id",
    "turn_id",
    "request_id",
    "question_driver_refs",
)


def build_q5_lane_prompt_context(
    *,
    source_context: dict[str, Any],
    lane_data_key: str,
    lane_data: dict[str, Any],
) -> dict[str, Any]:
    prompt_context = {
        key: deepcopy(source_context[key])
        for key in _PROMPT_METADATA_KEYS
        if source_context.get(key) not in (None, "", [], {})
    }
    prompt_context[lane_data_key] = deepcopy(lane_data)
    return prompt_context
