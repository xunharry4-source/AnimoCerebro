from __future__ import annotations

from pathlib import Path

from zentex.common.prompt_template_files import render_prompt_template

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")


def build_q8_external_system_prompt() -> str:
    return render_prompt_template(_TEMPLATE_DIR, "system_prompt.md", {}, error_prefix="q8_external")
