from __future__ import annotations

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


def build_plugin_generation_request(*, plugin_id: str, goal: str) -> dict[str, str]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the plugin generation role.",
            purpose="Focus the model on producing Zentex plugin artifacts.",
            content="You are an expert software engineer specialized in Zentex plugin architecture.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="goal",
            title="Goal",
            intent="Provide the target plugin goal.",
            purpose="Ground artifact generation in the requested plugin objective.",
            content=(
                f"- Plugin ID: {_clip_text(plugin_id, 120)}\n"
                f"- Goal: {_clip_text(goal, 1200)}"
            ),
        ),
        build_prompt_section(
            key="required_artifacts",
            title="Required Artifacts",
            intent="Define the files that must be produced.",
            purpose="Force the model to return a complete plugin bundle.",
            content="1. `plugin.py`\n2. `test_plugin.py`\n3. `README.md`",
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required JSON payload.",
            purpose="Prevent missing artifact fields.",
            content=(
                "Return strict JSON with keys:\n"
                "- `plugin_py`\n- `test_plugin_py`\n- `readme_md`\n- `diff_summary`\n"
                "All code must be ready to write to disk."
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
