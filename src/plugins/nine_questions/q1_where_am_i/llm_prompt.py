from __future__ import annotations

import json
from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
    trim_section_content,
)


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
                content=(
                "你是 Zentex 外部大脑层。你现在正在执行“九问驱动”的 Q1：我在那。\n"
                "你的任务是基于提供的客观证据，推断当前所处的物理环境与业务工作区领域。\n"
                "你必须进行绝对理性的分析，并严格按照要求的 JSON 格式输出 WorkspaceDomainInference 结果。"
                ),
            )
    ]
    prompt_sections = [
        build_prompt_section(
            key="input_evidence",
            title="输入证据 / User Context",
            intent="Provide preprocessed physical host, workspace structure, and sampled workspace content evidence.",
            purpose="Require Q1 to infer only from real preprocessed evidence.",
            content=(
                "以下是前置预处理证据（preprocessed_evidence）：\n"
                f"PhysicalHostState: {_to_prompt_json(physical_host_state)}\n\n"
                "WorkspaceStructureAnalyzer:\n"
                f"{trim_section_content(compressed.get('analysis_summary'))}\n\n"
                f"{trim_section_content(compressed.get('schema_summary'))}\n\n"
                "WorkspaceContentSampler:\n"
                f"{trim_section_content(compressed.get('sample_details'))}"
            ),
        ),
        build_prompt_section(
            key="output_constraint",
            title="输出约束 / Output Constraint",
            intent="Define the exact JSON-only WorkspaceDomainInference schema.",
            purpose="Prevent extra keys, prose outside JSON, or schema drift.",
            content=(
                "请基于上述证据，输出严格 JSON 对象，不得输出任何额外文本。\n"
                "输出必须且只能包含以下 6 个顶层字段，不得新增、删除或改名：\n"
                "{\n"
                '  "primary_domain": "string",\n'
                '  "secondary_domains": ["string", "string"],\n'
                '  "confidence": float (0.0到1.0之间),\n'
                '  "reasoning_summary": "string (解释你为何得出这些结论)",\n'
                '  "uncertainties": ["string (列出缺失的、需要进一步确认的信息)"],\n'
                '  "suggested_first_step": "string (建议的下一步探索或验证动作)"\n'
                "}\n"
                "字段含义与写入规则（逐条必须满足）：\n"
                "1) primary_domain：当前最可能的主工作区/业务领域。\n"
                "   - 含义：基于 PhysicalHostState、WorkspaceStructureAnalyzer 和 WorkspaceContentSampler 得出的主场景判断。\n"
                "   - 约束：必须是非空字符串，不得凭空引用未出现在证据中的外部环境。\n"
                "2) secondary_domains：可能并存的次级领域。\n"
                "   - 含义：代码库、文档、数据、测试、运维等混合场景中的辅助领域。\n"
                "   - 约束：必须是 string[]，可为空数组；元素不得重复。\n"
                "3) confidence：主领域判断置信度。\n"
                "   - 含义：0.0 到 1.0 的证据充分度，不是主观确信。\n"
                "   - 约束：必须是数字，低证据时必须降低置信度并在 uncertainties 中说明。\n"
                "4) reasoning_summary：证据链摘要。\n"
                "   - 含义：说明你引用了哪些目录、文件类型、采样片段或主机状态来得出结论。\n"
                "   - 约束：必须非空，不得写泛泛而谈的结论。\n"
                "5) uncertainties：不确定性列表。\n"
                "   - 含义：列出缺失、冲突、采样不足或需要进一步确认的信息。\n"
                "   - 约束：必须是非空 string[]；即使置信度较高，也至少说明一个剩余不确定性。\n"
                "6) suggested_first_step：下一步验证动作。\n"
                "   - 含义：建议一个低风险、可执行的后续探索/验证动作。\n"
                "   - 约束：必须非空，动作必须与当前证据直接相关。\n"
                "校验红线（硬性）：\n"
                "- 输出不可包含除上述 6 个字段外的任何字段。\n"
                "- 所有数组字段只能包含字符串。\n"
                "- 不得使用推断证据冒充实际扫描证据。"
            ),
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
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
