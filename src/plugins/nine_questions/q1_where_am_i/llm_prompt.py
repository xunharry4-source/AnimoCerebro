from __future__ import annotations

from typing import Any

from plugins.nine_questions.prompt_sections import (
    assemble_prompt_sections,
    build_prompt_section,
    trim_section_content,
)


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
            key="role",
            title="Role",
            intent="Establish the exact task identity for Q1.",
            purpose="Keep the model focused on environment inference instead of planning.",
            content=(
                "You are Zentex. Infer the current workspace domain (Q1: 我在哪). "
                "Return STRICT JSON that matches the WorkspaceDomainInference schema exactly."
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the exact output schema.",
            purpose="Prevent schema drift and missing required keys.",
            content=(
                "Required keys:\n"
                "- primary_domain (str)\n"
                "- secondary_domains (List[str])\n"
                "- confidence (float 0..1)\n"
                "- reasoning_summary (str)\n"
                "- uncertainties (List[str], must be non-empty)\n"
                "- suggested_first_step (str)"
            ),
        ),
        build_prompt_section(
            key="evidence_summary",
            title="Evidence Summary",
            intent="Provide the compressed workspace evidence.",
            purpose="Anchor the inference to local observable signals.",
            content=trim_section_content(compressed.get("analysis_summary")),
        ),
        build_prompt_section(
            key="local_stats",
            title="Local Stats",
            intent="Expose structural facts about the workspace.",
            purpose="Help the model infer domain from schema-level features.",
            content=trim_section_content(compressed.get("schema_summary")),
        ),
        build_prompt_section(
            key="uncertainty_hints",
            title="Uncertainty Hints",
            intent="Highlight ambiguous or weak evidence.",
            purpose="Force the answer to preserve uncertainty instead of overclaiming.",
            content=trim_section_content(compressed.get("uncertainty_summary")),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "analysis_summary": compressed.get("analysis_summary"),
        "sample_summary": compressed.get("sample_summary"),
        "schema_summary": compressed.get("schema_summary"),
        "uncertainty_summary": compressed.get("uncertainty_summary"),
        "suffix_distribution": suffix_distribution,
        "interpretation_markers": list(interpretation_markers or [])[:12],
        "risk_markers": list(risk_markers or [])[:12],
        "environment_event": environment_event,
        "physical_host_state": physical_host_state,
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
