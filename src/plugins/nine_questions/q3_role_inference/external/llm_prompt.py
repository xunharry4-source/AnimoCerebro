from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zentex.common.nine_questions_shared import json_safe_payload
from zentex.common.prompt_template_files import render_prompt_template

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")


def _json_block(value: Any) -> str:
    return json.dumps(json_safe_payload(value) if value is not None else {}, ensure_ascii=False, indent=2, default=str)


def _q3_external_template_values(context: dict[str, Any]) -> dict[str, str]:
    identity_kernel = context.get("identity_kernel_snapshot")
    q1_payload = context.get("q1_environment_confirmation")
    q2_external = context.get("q2_external_llm_output")
    if not isinstance(identity_kernel, dict) or not identity_kernel:
        raise RuntimeError("q3_external_identity_kernel_snapshot_missing")
    if not isinstance(q1_payload, dict) or not q1_payload:
        raise RuntimeError("q3_external_q1_environment_confirmation_missing")
    if not isinstance(q2_external, dict) or not q2_external:
        raise RuntimeError("q3_external_q2_external_llm_output_missing")
    return {
        "IdentityKernel_Snapshot": _json_block(identity_kernel),
        "Q1_EnvironmentConfirmation": _json_block(q1_payload),
        "Q2_ExternalSelfObservation": _json_block(q2_external),
    }


def build_q3_external_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    values = _q3_external_template_values(context)
    system_prompt = render_prompt_template(_TEMPLATE_DIR, "system_prompt.md", values, error_prefix="q3_external")
    user_prompt = render_prompt_template(_TEMPLATE_DIR, "user_prompt.md", values, error_prefix="q3_external")
    output_contract = render_prompt_template(_TEMPLATE_DIR, "output_contract.md", values, error_prefix="q3_external")
    full_prompt = f"{system_prompt}\n\n{user_prompt}\n\n{output_contract}"
    return {
        "system_prompt": system_prompt,
        "prompt": f"{user_prompt}\n\n{output_contract}",
        "full_prompt": full_prompt,
    }
