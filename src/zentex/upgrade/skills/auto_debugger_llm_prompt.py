from __future__ import annotations

from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


def build_root_cause_prompt(
    *,
    failure_stage: str,
    failure_reason: str,
    isolated_scope: list[str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the root-cause analysis role.",
            purpose="Focus the model on causal diagnosis rather than remediation.",
            content="Analyze the following upgrade failure and identify the root cause.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="failure_details",
            title="Failure Details",
            intent="Provide the failure evidence.",
            purpose="Ground the causal analysis in the observed failure.",
            content=(
                f"- Stage: {_clip_text(failure_stage, 200)}\n"
                f"- Error: {_clip_text(failure_reason, 1200)}\n"
                f"- Isolated Scope: {_clip_text(', '.join(isolated_scope), 800)}\n"
                f"- Payload Summary: {_clip_text(str(payload), 1500)}"
            ),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required RCA schema.",
            purpose="Require structured root cause output.",
            content=(
                "Return strict JSON with keys:\n"
                "- `immediate_cause`\n- `root_cause`\n- `triggering_condition`\n- `confidence`"
            ),
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain analysis quality.",
            purpose="Differentiate immediate symptoms from deeper causes.",
            content=(
                "1. Distinguish immediate cause from deeper root cause.\n"
                "2. `confidence` must be a float between 0.0 and 1.0.\n"
                "3. Do not output any explanation outside JSON."
            ),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
    }


def _clip_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return "[missing]"
    if len(text) <= limit:
        return text
    return text[:limit] + "... [truncated]"
