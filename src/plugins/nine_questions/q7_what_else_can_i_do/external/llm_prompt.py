from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.common.scoped_llm_prompt import build_scoped_llm_request

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")


def build_q7_external_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    return build_scoped_llm_request(
        question_id="q7",
        scope="external",
        template_dir=_TEMPLATE_DIR,
        context=context,
        title="Q7 External Creative Exploration",
        intent="Generate nonlinear external creative possibilities beyond current tools, assets, and Q4 objectives.",
        purpose="Keep Q7 external as creative exploration only; executable discoveries must return to Q4 before Q5/Q6.",
        error_prefix="q7_external",
    )
