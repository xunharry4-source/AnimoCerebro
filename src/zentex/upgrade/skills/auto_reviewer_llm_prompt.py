from __future__ import annotations

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


def build_code_review_prompt(*, code_snippets: list[str]) -> str:
    snippet_block = "\n\n".join(
        _clip_text(snippet, 2500)
        for snippet in code_snippets[:3]
    ) or "[no code snippets available]"
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the code-review role.",
            purpose="Focus the model on quality review of candidate code.",
            content="Review the following candidate code changes for quality issues.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="code_snippets",
            title="Code Snippets",
            intent="Provide the code under review.",
            purpose="Give the model the concrete candidate implementation to inspect.",
            content=snippet_block,
        ),
        build_prompt_section(
            key="review_intent",
            title="Review Intent",
            intent="Define the review dimensions.",
            purpose="Constrain the review to logic, performance, security, readability, and error handling.",
            content=(
                "Check for logic defects, performance risks, security issues beyond forbidden calls, "
                "readability problems, and missing error handling."
            ),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required review schema.",
            purpose="Require a strict review verdict and issue list.",
            content="Return strict JSON with keys:\n- `passed`\n- `issues`\n`issues` must be an array of short issue descriptions.",
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
    }


def _clip_text(value: str, limit: int) -> str:
    text = value.strip()
    if not text:
        return "[missing]"
    if len(text) <= limit:
        return text
    return text[:limit] + "... [truncated]"
