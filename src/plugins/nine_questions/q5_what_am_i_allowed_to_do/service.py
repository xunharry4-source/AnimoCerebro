from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_output_table import (
    NQ_BASELINE_SESSION_ID,
    load_llm_output_from_table,
)


def load_public_output(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return load_llm_output_from_table(db_path=db_path, session_id=session_id)
