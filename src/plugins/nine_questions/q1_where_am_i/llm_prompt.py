from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zentex.common.prompt_template_files import prompt_template_files, render_prompt_template
from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
    trim_section_content,
)

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_TEMPLATE_FILES = ["system_instruction.md", "input_evidence.md", "output_constraint.md"]


def _render_template(name: str, values: dict[str, str] | None = None) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values or {}, error_prefix="q1")


def _to_prompt_json(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(value or {})


def build_q1_llm_request(
    *,
    compressed: dict[str, Any],
    environment_event: dict[str, Any],
    physical_host_state: dict[str, Any],
    interpretation_markers: list[Any] | None,
    risk_markers: list[Any] | None,
    suffix_distribution: Any,
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="system_instruction",
            title="系统指令 / System Prompt",
            intent="Establish Q1 as environment awareness and situation interpretation.",
            purpose="Force rational inference from objective evidence and strict WorkspaceDomainInference JSON output.",
            content=_render_template("system_instruction.md"),
            )
    ]
    template_values = {
        "PHYSICAL_HOST_STATE_JSON": _to_prompt_json(physical_host_state),
        "ANALYSIS_SUMMARY": trim_section_content(compressed.get("analysis_summary")),
        "SCHEMA_SUMMARY": trim_section_content(compressed.get("schema_summary")),
        "SAMPLE_DETAILS": trim_section_content(compressed.get("sample_details")),
    }
    prompt_sections = [
        build_prompt_section(
            key="input_evidence",
            title="输入证据 / User Context",
            intent="Provide preprocessed physical host, workspace structure, and sampled workspace content evidence.",
            purpose="Require Q1 to infer only from real preprocessed evidence.",
            content=_render_template("input_evidence.md", template_values),
        ),
        build_prompt_section(
            key="output_constraint",
            title="输出约束 / Output Constraint",
            intent="Define the exact JSON-only WorkspaceDomainInference schema.",
            purpose="Prevent extra keys, prose outside JSON, or schema drift.",
            content=_render_template("output_constraint.md"),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "analysis_summary": compressed.get("analysis_summary"),
        "sample_summary": compressed.get("sample_summary"),
        "workspace_sample_details": compressed.get("sample_details"),
        "workspace_sample_payload": compressed.get("sample_payload"),
        "schema_summary": compressed.get("schema_summary"),
        "uncertainty_summary": compressed.get("uncertainty_summary"),
        "suffix_distribution": suffix_distribution,
        "interpretation_markers": list(interpretation_markers or [])[:12],
        "risk_markers": list(risk_markers or [])[:12],
        "environment_event": environment_event,
        "physical_host_state": physical_host_state,
        "template_files": prompt_template_files(_TEMPLATE_DIR, _TEMPLATE_FILES),
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
