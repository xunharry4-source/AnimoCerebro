from __future__ import annotations

from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


_MAX_PATTERNS = 3
_MAX_PATTERN_TEXT = 400
_MAX_PROPOSAL_TEXT = 1200


def build_atomic_planner_prompt(
    *,
    proposal: Any,
    patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    pattern_lines = "\n".join(
        f"- Pattern {index + 1}: {_clip_text(str(item.get('description') or '[missing]'), _MAX_PATTERN_TEXT)}"
        for index, item in enumerate(patterns[:_MAX_PATTERNS])
    ) or "- No historical success patterns available."
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the atomic planning role.",
            purpose="Focus the model on small executable upgrade tasks.",
            content="You are an expert upgrade planner. Break the proposal into atomic tasks.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="proposal",
            title="Proposal",
            intent="Provide the upgrade proposal.",
            purpose="Ground task generation in the actual upgrade target and impact.",
            content=(
                f"- Program ID: {_clip_text(getattr(proposal, 'program_id', ''), 200)}\n"
                f"- Target Metric: {_clip_text(getattr(proposal, 'target_metric', ''), 200)}\n"
                f"- Description: {_clip_text(getattr(proposal, 'description', ''), _MAX_PROPOSAL_TEXT)}\n"
                f"- Risk Score: {getattr(proposal, 'risk_score', 0.5)}\n"
                f"- Impact Score: {getattr(proposal, 'impact_score', 0.5)}"
            ),
        ),
        build_prompt_section(
            key="historical_patterns",
            title="Historical Patterns",
            intent="Provide prior success signals.",
            purpose="Reuse known successful upgrade planning patterns.",
            content=pattern_lines,
        ),
        build_prompt_section(
            key="planning_intent",
            title="Planning Intent",
            intent="Define the planning goal.",
            purpose="Require independent, dependency-aware, rollback-safe tasks.",
            content="Produce tasks that are independently executable, ordered by dependency, and safe to roll back.",
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required JSON schema.",
            purpose="Prevent missing fields and free-form output.",
            content=(
                "Return strict JSON with top-level key `tasks`.\n"
                "Each task must include:\n"
                "- `task_id`\n- `description`\n- `file_paths`\n- `code_changes`\n"
                "- `validation_commands`\n- `estimated_time_minutes`\n"
                "- `dependencies`\n- `rollback_instructions`"
            ),
        ),
        build_prompt_section(
            key="hard_constraints",
            title="Hard Constraints",
            intent="Constrain task granularity and realism.",
            purpose="Keep generated tasks atomic and executable.",
            content=(
                "1. Each task must be completable in 2-5 minutes.\n"
                "2. File paths must be concrete.\n"
                "3. Validation commands must be executable shell commands.\n"
                "4. Order must reflect dependencies.\n"
                "5. Do not add explanation outside JSON."
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
