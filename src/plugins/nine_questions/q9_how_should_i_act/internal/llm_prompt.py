from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.common.scoped_llm_prompt import build_scoped_llm_request

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")


def build_q9_internal_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    return build_scoped_llm_request(
        question_id="q9",
        scope="internal",
        template_dir=_TEMPLATE_DIR,
        context=context,
        title="Q9 Action Design",
        intent="Generate an internal action design only from the internal context passed to this branch.",
        purpose="Keep Q9 internal action design separate from external execution design.",
        error_prefix="q9_internal",
    )
