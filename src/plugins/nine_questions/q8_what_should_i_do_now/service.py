from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.nine_questions.q8_what_should_i_do_now.llm_output_table import (
    NQ_BASELINE_SESSION_ID,
    load_external_llm_output_from_table,
    load_internal_llm_output_from_table,
)


def load_internal_public_output(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return load_internal_llm_output_from_table(db_path=db_path, session_id=session_id)


def load_external_public_output(
    *,
    db_path: str | Path | None = None,
    session_id: str = NQ_BASELINE_SESSION_ID,
) -> dict[str, Any]:
    return load_external_llm_output_from_table(db_path=db_path, session_id=session_id)
