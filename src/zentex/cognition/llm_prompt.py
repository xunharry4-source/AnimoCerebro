from __future__ import annotations

from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


def build_interaction_mind_prompt() -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the interaction-mind inference role.",
            purpose="Focus the model on internal understanding-state inference.",
            content="Infer the other party's intent, knowledge gaps, communication fit, and misunderstanding signals.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required interaction-mind schema.",
            purpose="Require a complete social-mind state payload.",
            content="Return strict JSON with keys:\n- `model`\n- `knowledge_gap`\n- `communication_fit`\n- `misunderstanding_signals`",
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain the scope of inference.",
            purpose="Prevent the model from suggesting actions or side effects.",
            content="Only infer internal understanding state. Do not suggest actions or external side effects.",
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
    }


def build_simulation_comparison_prompt(*, goal_id: str, branch_count: int) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the branch-comparison role.",
            purpose="Focus the model on structured comparison across simulated branches.",
            content="Compare the simulated branches and produce a structured decision summary.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="input_summary",
            title="Input Summary",
            intent="Provide the simulation comparison scope.",
            purpose="Ground the comparison in the current goal and number of branches.",
            content=f"- Goal ID: {_clip_text(goal_id, 120)}\n- Branch Count: {branch_count}",
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the comparison schema.",
            purpose="Require summary, ranking, and recommendation in a structured format.",
            content="Return strict JSON with keys:\n- `summary`\n- `risk_ranking`\n- `recommended_branch_id`",
        ),
        build_prompt_section(
            key="quality_rules",
            title="Quality Rules",
            intent="Constrain the basis of comparison.",
            purpose="Prevent unsupported recommendations.",
            content="Explain relative risk and select the recommended branch based on the supplied simulation evidence only.",
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
    }


def _clip_text(value: Optional[str], limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return "[missing]"
    if len(text) <= limit:
        return text
    return text[:limit] + "... [truncated]"
