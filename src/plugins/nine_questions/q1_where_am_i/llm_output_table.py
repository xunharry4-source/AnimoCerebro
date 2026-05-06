from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.nine_questions.llm_output_table import load_question_llm_output_from_table


def load_llm_output_from_table(*, db_path: str | Path | None = None, session_id: str = "nq-baseline") -> dict[str, Any]:
    return load_question_llm_output_from_table("q1", db_path=db_path, session_id=session_id)
