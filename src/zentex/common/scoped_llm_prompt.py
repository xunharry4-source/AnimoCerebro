from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section
from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template

_RUNTIME_CONTEXT_KEYS = {
    "audit_service",
    "audit_store",
    "environment_service",
    "foundation_service",
    "learning_service",
    "llm_service",
    "memory_service",
    "model_provider",
    "module_run_persistor",
    "plugin_registry",
    "plugin_service",
    "reflection_service",
    "root_audit_store",
    "root_transcript_store",
    "transcript_store",
}


def json_block(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2, default=str)


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    return None


def _scoped_model_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): _json_safe_payload(value)
        for key, value in context.items()
        if str(key) not in _RUNTIME_CONTEXT_KEYS
    }


def build_scoped_llm_request(
    *,
    question_id: str,
    scope: str,
    template_dir: Path,
    context: dict[str, Any],
    title: str,
    intent: str,
    purpose: str,
    error_prefix: str,
) -> dict[str, Any]:
    files = ["system_prompt.md", "user_prompt.md", "output_contract.md"]
    model_context = _scoped_model_context(context)
    values = {"CONTEXT_JSON": json_block(model_context)}
    system_prompt_sections = [
        build_prompt_section(
            key=f"{scope}_role",
            title=f"{title} {scope.title()} Role",
            intent=intent,
            purpose=purpose,
            content=render_prompt_template(template_dir, "system_prompt.md", values, error_prefix=error_prefix),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key=f"{scope}_context",
            title=f"{title} {scope.title()} Context",
            intent=f"Provide {question_id.upper()} {scope} evidence through a file template.",
            purpose="Keep prompt inputs explicit and auditable.",
            content=render_prompt_template(template_dir, "user_prompt.md", values, error_prefix=error_prefix),
        ),
        build_prompt_section(
            key=f"{scope}_output_contract",
            title=f"{title} {scope.title()} Output Contract",
            intent=f"Define {question_id.upper()} {scope} JSON output.",
            purpose="Prevent schema drift and free-form text.",
            content=render_prompt_template(template_dir, "output_contract.md", values, error_prefix=error_prefix),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": {
            "question_id": question_id,
            "scope": scope,
            "context": model_context,
            "template_files": prompt_template_files(template_dir, files),
        },
    }
