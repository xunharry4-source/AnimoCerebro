from __future__ import annotations

from plugins.nine_questions.q5_what_am_i_allowed_to_do.external.service import (
    run_q5_external_llm_and_save,
)
from .llm_prompt import build_q5_external_llm_request

__all__ = [
    "build_q5_external_llm_request",
    "run_q5_external_llm_and_save",
]
