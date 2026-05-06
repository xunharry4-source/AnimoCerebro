from __future__ import annotations

import json
from typing import Any

from zentex.common.nine_questions_prompts import (
    build_prompt_section,
)


def _json_module(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _render_template(template: str, replacements: dict[str, str]) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    unresolved = [part.split("}}", 1)[0] for part in rendered.split("{{")[1:] if "}}" in part]
    if unresolved:
        raise RuntimeError(f"Q3 prompt template has unresolved placeholders: {sorted(set(unresolved))}")
    return rendered.strip()


# Q3 提示词锁定说明：
# 以下系统提示词是用户指定的 Q3 唯一正确业务契约，禁止擅自修改、压缩、重写、兼容或降级。
# 如需变更，必须先取得用户明确许可，并同步修改 Q3 输出校验、模型与验收测试。
Q3_SYSTEM_PROMPT_TITLE = """# [系统指令 / System Prompt: Zentex Q3 角色推断与人类意志对齐中枢]"""


Q3_SYSTEM_PROMPT_ROLE_AND_REDLINE = """你是 Zentex (AnimoCerebro) 九问驱动框架 Q3 阶段（“我是谁？”）的角色推断与人类意志对齐中枢。
你的核心职责是：基于当前的环境态势与系统资产，推断出最适合当前场景的任务角色，同时生成系统的使命与连续性边界。
**【最高安全红线 - 人类意志绝对优先】：如果系统上下文中存在用户手动锁定的工作角色，你必须将其原封不动地填入 `active_role` 字段！绝对禁止擅自改写、简化或替换用户的角色设定！即使用户设定的角色与当前环境完全脱节，你也必须严格遵守，并只能在偏差字段中抛出警告。**
**【架构纯净要求】：你必须使用纯净的自然语言，绝对禁止在输出中编造或混入任何内部系统工程代号。**"""


Q3_SYSTEM_PROMPT_INPUTS = """---

## 📥 一、 强制输入上下文规范 (Inputs)
你必须基于以下传入的前置数据状态进行角色推断。上下文中将严格包含以下结构化对象与核心字段，你必须精准提取，严禁自行脑补：

1. **[Q1_Environment_State]**：Q1 阶段传来的环境态势。你必须重点读取核心业务域与态势总结。
2. **[Q2_Asset_Inventory]**：Q2 阶段传来的软性资产大盘。你必须重点读取系统当前真实可调用的工具与智能体。
3. **[Identity_Kernel]**：系统持久化的身份内核。你必须严格读取并遵循以下字段：
   - `identity_role`：**底层基础身份的名称。它确立了系统最基础的本体标识（System's Base Identity），你必须提取报告该基础身份，但其字面字符串不应主导最终的任务执行角色设定。**
   - `meta_drive`：系统的底层元动机。
   - `continuity_boundaries` / `prohibitions`：系统在任何角色下都绝对不能跨越的行为红线与禁令。
4. **[Human_Intervention_Receipts]**：近期的人工干预与用户指令。若包含用户明确指定或锁定的当前工作角色，必须无条件服从并用于填充 `active_role`。"""


Q3_SYSTEM_PROMPT_SCHEMA = """---

## 📤 二、 严格 JSON 格式与详细字段说明 (Strict Output Schema)
你的输出必须是合法的纯 JSON 对象。根节点强制为 `Q3InferenceResult`，且必须精确包含以下两个核心对象：

### 1. `RoleProfile` (三层角色模型)
*   **`identity_role` (String)**: 底层不可变主体身份。**【唯一性约束】该值必须来源于 [Identity_Kernel]，但它代表的是系统执行的内核名称，其输出的字面值应进行概念抽象，不应直接作为任务角色的候选值，仅作为身份溯源标记。该语义应抽象为“AI系统本体”级别。**
*   **`active_role` (String)**: **【人类意志优先】** 当前执行角色。如果输入 `[Human_Intervention_Receipts]` 中存在用户锁定的角色设定，必须强制填充该设定并附带 `[User Locked]` 标记；若无用户设定，可回退为系统结合环境推断的角色。
*   **`inferred_reference_role` (String)**: 环境参考角色。基于环境态势与系统资产独立推演出当前环境最需要的角色（纯客观推演，不受用户锁定影响，也不受 identity_role 字面值干扰）。
*   **`role_alignment_gap` (String)**: 角色偏差与建议。对比 `active_role` 和 `inferred_reference_role`。若严重错位，必须在此抛出明确的冲突说明与能力缺口风险，并给出业务化提示。若一致则填“无明显偏差”。
*   **`task_role` (String)**: 任务切面角色。为了解决当前具体子问题而临时扮演的动态且细粒度的切面角色。

### 2. `MissionContinuityBoundary` (使命与连续性边界)
*   **`current_mission` (String)**: 根据当前环境和角色，推断出的当前核心主线使命。
*   **`priority_duties` (Array of Strings)**: 当前 `active_role` 应当优先履行的核心职责列表。
*   **`continuity_boundaries` (Array of Strings)**: **【最高防御底线】** 连续性红线与底层禁令。必须从输入的 `[Identity_Kernel]` 中精准提取系统在任何角色、任何任务下都绝对不能跨越的行为边界和禁令列表，禁止遗漏。"""


Q3_SYSTEM_PROMPT_STRICT_JSON_TEMPLATE = """---

## 📝 三、 强制 JSON 输出结构范例 (Strict JSON Template)

{
  "Q3InferenceResult": {
    "RoleProfile": {
      "identity_role": "Zentex 独立外部大脑",
      "active_role": "财务审计顾问 [User Locked]",
      "inferred_reference_role": "Linux服务器运维工程师",
      "role_alignment_gap": "当前 Q1 环境为后端代码库与 Nginx 错误日志，系统客观推断最匹配角色为运维工程师。但用户干预指令中强制锁定了'财务审计顾问'。警告：可能存在严重的领域知识不匹配与外部工具调用能力缺失。建议：采纳系统建议角色以提升排障效率。",
      "task_role": "日志解析与错误提取专员"
    },
    "MissionContinuityBoundary": {
      "current_mission": "在遵守审计严谨性的前提下，分析当前目录下的异常报错流并定位根因。",
      "priority_duties": [
        "确保所有操作具备审计留痕",
        "以只读模式梳理系统错误时间线"
      ],
      "continuity_boundaries": [
        "绝对禁止在未获授权的情况下删除宿主的任何日志文件",
        "绝对禁止向外部公网发送包含敏感密钥的分析结果"
      ]
    }
  }
}"""


Q3_SYSTEM_PROMPT_TEMPLATE = "\n\n".join(
    [
        Q3_SYSTEM_PROMPT_TITLE,
        Q3_SYSTEM_PROMPT_ROLE_AND_REDLINE,
        Q3_SYSTEM_PROMPT_INPUTS,
        Q3_SYSTEM_PROMPT_SCHEMA,
        Q3_SYSTEM_PROMPT_STRICT_JSON_TEMPLATE,
    ]
)


Q3_USER_PROMPT_TEMPLATE = """
你必须按下面的模块顺序推理。模块是替换后的结构化输入，不是可自由拼接解释文本。

<Q3_PROMPT_MODULE id="Q1_Environment_State">
{{Q1_ENVIRONMENT_STATE_MODULE}}
</Q3_PROMPT_MODULE>

<Q3_PROMPT_MODULE id="Q2_Asset_Inventory">
{{Q2_ASSET_INVENTORY_MODULE}}
</Q3_PROMPT_MODULE>

<Q3_PROMPT_MODULE id="Identity_Kernel">
{{IDENTITY_KERNEL_MODULE}}
</Q3_PROMPT_MODULE>

<Q3_PROMPT_MODULE id="Human_Intervention_Receipts">
{{HUMAN_INTERVENTION_RECEIPTS_MODULE}}
</Q3_PROMPT_MODULE>

<Q3_PROMPT_MODULE id="Strict_Output_Contract">
{{OUTPUT_CONTRACT_MODULE}}
</Q3_PROMPT_MODULE>

执行顺序：
1. 从 [Q1_Environment_State] 读取 `primary_domain` / `secondary_domains` / `reasoning_summary`。
2. 从 [Q2_Asset_Inventory] 读取 `available_tools` / `external_agents` / `reusable_strategy_patches`。
3. 从 [Identity_Kernel] 读取 `identity_role` 作为身份溯源依据，并输出概念抽象后的“AI系统本体”级身份标记；不得把它作为 `active_role` 或 `inferred_reference_role` 的候选值。
4. 从 [Human_Intervention_Receipts] 判断是否存在 `locked_active_role`。若存在，`RoleProfile.active_role` 必须原封不动使用该值并附带 `[User Locked]` 标记。
5. 独立推断 `RoleProfile.inferred_reference_role`，并把 active_role 与 inferred_reference_role 的偏差只写入 `RoleProfile.role_alignment_gap`。
6. 只输出 Strict_Output_Contract 指定 JSON。不得输出 Markdown、解释文字、内部系统工程代号或额外字段。
"""


Q3_INVOCATION_PROMPT_TEMPLATE = """
<Q3_SYSTEM_INSTRUCTION>
{{SYSTEM_PROMPT}}
</Q3_SYSTEM_INSTRUCTION>

<Q3_RENDERED_USER_PROMPT>
{{USER_PROMPT}}
</Q3_RENDERED_USER_PROMPT>

<Q3_RETRY_HINT>
{{RETRY_HINT}}
</Q3_RETRY_HINT>
"""


def build_q3_role_llm_request(
    *,
    risk_weight: float,
    q1_llm_output: dict[str, Any],
    q2_llm_output: dict[str, Any],
    identity_kernel_snapshot: dict[str, Any],
    role_payload: dict[str, Any],
    constraint_payload: dict[str, Any],
    manual_role_overrides: dict[str, Any],
) -> dict[str, Any]:
    prompt_modules: dict[str, Any] = {
        "Q1_Environment_State": {
            "module_contract": "Q1 authoritative environment state.",
            "q1_authoritative_llm_output": q1_llm_output,
        },
        "Q2_Asset_Inventory": {
            "module_contract": "Q2 authoritative asset inventory for Q3 role inference.",
            "available_tools": q2_llm_output.get("available_tools") or q2_llm_output.get("q2_external_tool_asset_inventory") or [],
            "external_agents": q2_llm_output.get("external_agents") or [],
            "reusable_strategy_patches": q2_llm_output.get("reusable_strategy_patches") or [],
            "q2_authoritative_llm_output": q2_llm_output,
        },
        "Identity_Kernel": {
            "module_contract": "Authoritative identity kernel. RoleProfile.identity_role must be sourced from this module and abstracted as an AI system ontology marker, not used as a task role candidate.",
            "identity_kernel_snapshot": identity_kernel_snapshot,
            "role_payload": role_payload,
            "constraint_payload": constraint_payload,
        },
        "Human_Intervention_Receipts": {
            "module_contract": "Authoritative human intervention receipts. If locked_active_role is present, RoleProfile.active_role must use it exactly and append [User Locked].",
            "locked_active_role": manual_role_overrides.get("active_role_override") or manual_role_overrides.get("locked_active_role"),
            "user_instructions": manual_role_overrides.get("user_instructions") or [],
            "manual_role_overrides": manual_role_overrides,
        },
        "Strict_Output_Contract": {
            "required_model_output_top_level_keys": ["Q3InferenceResult"],
            "Q3InferenceResult_keys": ["RoleProfile", "MissionContinuityBoundary"],
            "RoleProfile_keys": [
                "identity_role",
                "active_role",
                "inferred_reference_role",
                "role_alignment_gap",
                "task_role",
            ],
            "MissionContinuityBoundary_keys": [
                "current_mission",
                "priority_duties",
                "continuity_boundaries",
            ],
            "pre_output_validations": [
                "The root object must contain exactly Q3InferenceResult.",
                "Q3InferenceResult must contain exactly RoleProfile and MissionContinuityBoundary.",
                "RoleProfile.identity_role must be sourced from Identity_Kernel and abstracted as AI system ontology.",
                "If Human_Intervention_Receipts.locked_active_role exists, RoleProfile.active_role must preserve it and include [User Locked].",
                "RoleProfile.role_alignment_gap is the only place where disagreement with a user locked role may be expressed.",
                "MissionContinuityBoundary.continuity_boundaries must not be empty and must inherit Identity_Kernel continuity_boundaries/prohibitions.",
                "The first character must be { and the last character must be }.",
            ],
            "strict_json_only": True,
            "risk_weight": risk_weight,
        },
    }
    system_prompt_sections = [
        build_prompt_section(
            key="system_instruction",
            title="Q3 locked system prompt",
            intent="Define Q3 role inference and human-will alignment without modifying user role.",
            purpose="Bind Q3 to the user-approved Q3InferenceResult JSON contract.",
            content=Q3_SYSTEM_PROMPT_TEMPLATE.strip(),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key=key,
            title=f"Q3 module: {key}",
            intent="Rendered Q3 prompt module",
            purpose="Auditable module injected through template replacement.",
            content=_json_module(value),
        )
        for key, value in prompt_modules.items()
    ]
    system_prompt = _render_template(Q3_SYSTEM_PROMPT_TEMPLATE, {})
    prompt = _render_template(
        Q3_USER_PROMPT_TEMPLATE,
        {
            "Q1_ENVIRONMENT_STATE_MODULE": _json_module(prompt_modules["Q1_Environment_State"]),
            "Q2_ASSET_INVENTORY_MODULE": _json_module(prompt_modules["Q2_Asset_Inventory"]),
            "IDENTITY_KERNEL_MODULE": _json_module(prompt_modules["Identity_Kernel"]),
            "HUMAN_INTERVENTION_RECEIPTS_MODULE": _json_module(prompt_modules["Human_Intervention_Receipts"]),
            "OUTPUT_CONTRACT_MODULE": _json_module(prompt_modules["Strict_Output_Contract"]),
        },
    )
    combined_prompt = _render_template(
        Q3_INVOCATION_PROMPT_TEMPLATE,
        {
            "SYSTEM_PROMPT": system_prompt,
            "USER_PROMPT": prompt,
            "RETRY_HINT": "",
        },
    )
    model_context = {
        "q3_prompt_modules": prompt_modules,
        "q3_prompt_template": Q3_USER_PROMPT_TEMPLATE,
        "q3_invocation_prompt_template": Q3_INVOCATION_PROMPT_TEMPLATE,
        "risk_weight": risk_weight,
        "llm_temperature": 0.0,
        "llm_max_output_tokens": 1536,
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "combined_prompt": combined_prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "prompt_modules": prompt_modules,
        "model_context": model_context,
    }
