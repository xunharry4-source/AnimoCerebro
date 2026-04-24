from __future__ import annotations

from typing import Any

from zentex.common.prompt_sections import assemble_prompt_sections, build_prompt_section


_MAX_OBJECTIVE = 1200
_MAX_METRIC = 300
_MAX_LOGS = 10
_MAX_LOG_TEXT = 600


def build_dspy_primitive_generation_request(
    *,
    objective_summary: str,
    target_metric: str,
) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the DSPy primitive generation role.",
            purpose="Focus the model on code-producing prompt optimization primitives.",
            content=(
                "You are a DSPy expert. Generate production-oriented DSPy primitives "
                "that match the stated optimization objective."
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="objective",
            title="Objective",
            intent="Provide the optimization objective.",
            purpose="Ground the primitive design in the real optimization target.",
            content=_clip_text(objective_summary, _MAX_OBJECTIVE),
        ),
        build_prompt_section(
            key="target_metric",
            title="Target Metric",
            intent="Provide the metric to optimize.",
            purpose="Constrain generated primitives to the intended evaluation signal.",
            content=_clip_text(target_metric, _MAX_METRIC),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the required JSON code bundle.",
            purpose="Ensure the model returns a complete code package.",
            content=(
                "Return strict JSON with keys:\n"
                "- `signature`\n- `module`\n- `metric`\n"
                "Each value must be valid Python source code as a string."
            ),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
    }


def build_optimization_needs_request(failure_logs: list[dict[str, Any]]) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the failure-pattern analysis role.",
            purpose="Focus the model on optimization opportunity discovery.",
            content="Analyze failure patterns and propose high-value LLM optimization candidates.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="analysis_task",
            title="Analysis Task",
            intent="Define the reasoning task over the failure logs.",
            purpose="Tell the model what kind of optimization findings to extract.",
            content=(
                "Analyze the supplied failure logs and identify recurring optimization opportunities."
            ),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the expected optimization findings.",
            purpose="Prevent vague summaries and require actionable candidate directions.",
            content=(
                "Return strict JSON describing candidate optimization directions, "
                "affected components, and the failure patterns that justify them."
            ),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": {"failure_logs": _limit_records(failure_logs)},
    }


def build_target_identification_request(failure_history: list[dict[str, Any]]) -> dict[str, Any]:
    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the optimization target prioritization role.",
            purpose="Keep the model focused on prioritizing next capability investments.",
            content="Prioritize which LLM capabilities and metrics should be optimized next.",
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="analysis_task",
            title="Analysis Task",
            intent="Define the capability-prioritization task.",
            purpose="Tell the model to rank capabilities and metrics from failure history.",
            content="Identify which component capabilities and evaluation metrics should be prioritized.",
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the expected findings schema.",
            purpose="Require a structured findings array instead of a narrative answer.",
            content=(
                "Return strict JSON with a top-level `findings` array. "
                "Each finding should explain the target capability, why it matters, and which signals support it."
            ),
        ),
    ]
    return {
        "system_prompt": assemble_prompt_sections(system_prompt_sections),
        "prompt": assemble_prompt_sections(prompt_sections),
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": {"history": _limit_records(failure_history)},
    }


def _limit_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limited: list[dict[str, Any]] = []
    for item in records[:_MAX_LOGS]:
        normalized: dict[str, Any] = {}
        for key, value in item.items():
            if isinstance(value, str):
                normalized[key] = _clip_text(value, _MAX_LOG_TEXT)
            else:
                normalized[key] = value
        limited.append(normalized)
    return limited


def _clip_text(value: Optional[str], limit: int) -> str:
    text = (value or "").strip()
    if not text:
        return "[missing]"
    if len(text) <= limit:
        return text
    return text[:limit] + "... [truncated]"
