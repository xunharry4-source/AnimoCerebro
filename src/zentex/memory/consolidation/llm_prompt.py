from __future__ import annotations

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


def build_consolidation_summary_prompt() -> dict[str, str | list[dict[str, str]]]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the memory consolidation summarization role.",
            purpose="Focus the model on long-term reusable memory extraction.",
            content="Summarize the reusable memory value of the supplied memory fragments.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the consolidation summary schema.",
            purpose="Require a structured summary of reusable memory and compression.",
            content="Return strict JSON with keys:\n- `summary`\n- `promotion_candidates`\n- `compressed_refs`",
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain consolidation quality.",
            purpose="Prioritize durable knowledge over raw transcript repetition.",
            content=(
                "Focus on long-term reusable knowledge, low-value compression opportunities, "
                "and promotion candidates justified by repeated patterns."
            ),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
    }
