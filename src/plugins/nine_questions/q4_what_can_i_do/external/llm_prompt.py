from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_TEMPLATE_FILES = ["system_prompt.md", "user_prompt.md", "output_contract.md"]
_Q4_EXTERNAL_CONTEXT_KEYS = (
    "Q3_ExternalDelegationPosture",
    "Q1_EnvironmentObjectiveSignal_External",
    "Q2_SelfObservationObjectiveSignal_External",
    "Q1Q2_FusedObjectiveSignal_External",
    "Reflection_CapabilityGapSignal_External",
    "CapabilityBoundaryEvidence_External",
    "UserManualTaskGoalLaneAnalysis",
)


def _json_block(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2, default=str)


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="q4_external")


def _q4_external_context_variables(context: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in _Q4_EXTERNAL_CONTEXT_KEYS if key not in context]
    if missing:
        raise RuntimeError(f"q4_external_context_variables_missing:{','.join(missing)}")
    return {key: context.get(key) for key in _Q4_EXTERNAL_CONTEXT_KEYS}


def build_q4_external_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    context_variables = _q4_external_context_variables(context)
    values = {key: _json_block(value) for key, value in context_variables.items()}
    system_prompt = _render_template("system_prompt.md", values)
    user_prompt = _render_template("user_prompt.md", values)
    output_contract = _render_template("output_contract.md", values)
    full_prompt = f"{system_prompt}\n\n{user_prompt}\n\n{output_contract}"
    return {
        "system_prompt": system_prompt,
        "prompt": f"{user_prompt}\n\n{output_contract}",
        "full_prompt": full_prompt,
        "model_context": {
            "q4_external_context_variables": context_variables,
            "template_files": prompt_template_files(_TEMPLATE_DIR, _TEMPLATE_FILES),
        },
    }
