from __future__ import annotations

import json
from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


def build_q5_llm_request(
    *,
    authorization_baseline: dict[str, Any],
    rendered_q4_boundary: str,
    actionable_space: list[str],
    snapshot_version: Any,
    q4_capability_boundary_profile: dict[str, Any],
    q4_permission_profile: Any,
    contact_policy: Any,
    tenant_scope: Any,
    agent_trust_policy: Any,
    q2_connected_agents: Any,
    functional_authorization_inputs: list[dict[str, Any]],
    identity_kernel: dict[str, Any],
    question_driver_refs: list[str],
) -> dict[str, Any]:
    preprocessed_evidence = {
        "identity_kernel_lock_and_self_binding": identity_kernel,
        "host_agent_and_environment_permissions": {
            "q4_capability_boundary_profile": q4_capability_boundary_profile,
            "q4_permission_profile": q4_permission_profile,
            "rendered_q4_boundary": rendered_q4_boundary,
            "actionable_space": actionable_space,
            "authorization_baseline": authorization_baseline,
            "functional_authorization_inputs": functional_authorization_inputs[:12],
        },
        "multi_brain_social_collaboration_willingness": {
            "contact_policy": contact_policy,
            "tenant_scope": tenant_scope,
            "agent_trust_policy": agent_trust_policy,
            "q2_connected_agents": q2_connected_agents,
        },
        "question_driver_refs": question_driver_refs,
        "snapshot_version": snapshot_version,
    }
    system_prompt_sections = [
        build_prompt_section(
            key="system_instruction",
            title="系统指令 / System Prompt",
            intent="Define the strict cannot-do boundary task for Q5.",
            purpose="Keep the model focused on forbidden, denied, and escalation-required actions, not raw capability.",
            content=(
                "# [系统指令 / System Prompt: Zentex Q5 我不能干什么 / 禁止边界与合规中枢 (纯净版)]\n\n"
                "你是 Zentex (AnimoCerebro) 九问驱动框架的 Q5 阶段核心认知中枢。\n"
                "你的核心职责是：基于当前系统的能力、角色以及底层策略，回答“我不能干什么”，并界定系统的“禁止边界 / Cannot-Do Boundary”。\n"
                "【最高安全红线 - 最小特权原则】：你必须优先识别禁止动作、未授权动作、需要升级审批的动作。"
                "允许动作只作为对照白名单存在，不得抢占 Q4 的能力判断，也不得给 Q6 重复制造红线所有权。\n\n"
                "一、强制输入上下文规范 (Inputs)\n"
                "你必须基于以下输入进行客观推演：\n"
                "1. [Q3_RoleProfile]：当前绑定的主体执行角色与使命，决定了你的业务行为初衷。\n"
                "2. [Q4_Capabilities]：Q4 评估出的“已验证能力 (verified_capabilities)”。你不能授权系统去做它根本不会做的事。\n"
                "3. [Security_Policies & Identity]：底层注入的安全红线、租户隔离策略、跨脑联系策略以及身份内核禁令。\n\n"
                "二、严格 JSON 格式与详细字段说明 (Strict JSON Schema)\n"
                "你的输出必须是合法的纯 JSON 对象。根节点必须强制包含 `AuthorizationBoundary` 对象。\n"
                "`AuthorizationBoundary` 必须包含 5 个必填字段：\n"
                "1. `current_authorization_scope` (String)：当前禁止边界总体描述。用一句话精准概括当前系统在本次交互中不能越过的最高权限域。\n"
                "2. `communication_policy` (String)：联系策略。明确当前系统与用户、其他 Agent、外部网络的通信权限；必须说明是否允许多脑广播、是否允许外部 HTTP 请求、是否只允许向人类求助。\n"
                "3. `organizational_boundary` (String)：组织边界。明确当前主体在组织拓扑或租户隔离层面的边界。\n"
                "4. `allowed_operations` (Array of Strings)：允许操作对照白名单。任何允许操作必须由 Q4 已验证能力支撑，且只能用于证明 forbidden_operations 的裁剪范围。\n"
                "5. `forbidden_operations` (Array of Strings)：禁止操作黑名单。任何未授权、需升级审批、命中 Security_Policies & Identity 禁令、超出租户/联系边界或缺少 Q4 能力证据的动作必须写入此处。\n\n"
                "三、输出前强制拦截与自检红线 (Pre-Output Validations)\n"
                "在生成 JSON 前，你必须在后台模拟执行以下安全检查：\n"
                "1. 禁止边界优先：先生成 `forbidden_operations`，再生成用于对照的 `allowed_operations`。\n"
                "2. 权限收口拦截：检查 `allowed_operations`。如果出现 Q4 没有验证过的能力，必须立刻移入 `forbidden_operations`。\n"
                "3. 禁令继承拦截：检查 `forbidden_operations`。必须确保安全策略、身份内核、tenant/contact/trust 约束明确声明的禁止项全量继承。\n"
                "4. 纯 JSON 输出：确保第一行是 `{`，最后一行是 `}`，无任何 Markdown 包装。"
            ),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="user_context",
            title="输入证据 / User Context",
            intent="Provide Q5 preprocessed cannot-do evidence.",
            purpose="Ground forbidden operations in identity, host permissions, and collaboration trust signals.",
            content=(
                "以下是前置预处理证据（preprocessed_evidence）：\n"
                "1. [Q3_RoleProfile]：来自身份内核锁、自我绑定、Q3 role profile 与 mission boundary。\n"
                "2. [Q4_Capabilities]：来自 Q4 capability boundary、permission profile、rendered boundary 与 actionable_space。\n"
                "3. [Security_Policies & Identity]：来自身份边界、tenant_scope、contact_policy、agent_trust_policy、workspace forbidden actions 与功能授权插件输入。\n\n"
                f"{json.dumps(preprocessed_evidence, ensure_ascii=False, indent=2)}"
            ),
        ),
        build_prompt_section(
            key="authorization_guard",
            title="禁止边界防线 / Cannot-Do Guard",
            intent="Constrain forbidden and allowed actions to formal policy evidence.",
            purpose="Prevent Q5 from widening Q4 capability or bypassing tenant/contact policy.",
            content=(
                "- `forbidden_operations` 是 Q5 主输出语义；所有未授权、需升级、缺证据、越租户、越联系边界的动作必须进入该字段。\n"
                "- `allowed_operations` 必须是 Q4 actionable_space 的子集；不得发明、扩写或改写 Q4 没有给出的动作。\n"
                "- 如果某动作物理可执行但没有明确授权，或命中 tenant_scope、contact_policy、agent_trust_policy、身份边界禁令，必须写入 `forbidden_operations`。\n"
                "- 如果 contact_policy、tenant_scope 或 agent_trust_policy 表明协作不可用或受限，必须在 `communication_policy` 和 `organizational_boundary` 中明确说明。\n"
                "- 禁止输出 `question_driver_refs` 或任何 schema 外字段；证据来源由运行时审计记录维护。"
            ),
        ),
        build_prompt_section(
            key="output_constraint",
            title="输出约束 / Output Constraint",
            intent="Define the exact cannot-do boundary schema.",
            purpose="Reject legacy profile schemas and open-ended authorization prose.",
            content=(
                "请基于上述证据，输出 JSON 结构，必须且只能包含以下根节点与键值：\n"
                "{\n"
                '  "AuthorizationBoundary": {\n'
                '    "current_authorization_scope": "string (当前禁止边界总体描述)",\n'
                '    "communication_policy": "string (用户、其他 Agent、外部网络、多脑广播、HTTP 请求、人类求助的联系策略)",\n'
                '    "organizational_boundary": "string (组织拓扑、租户隔离、项目/实例边界)",\n'
                '    "allowed_operations": ["string (Q4 已验证能力支撑且未命中禁止边界的对照白名单)"],\n'
                '    "forbidden_operations": ["string (未授权、需升级审批、安全策略、身份内核、租户隔离、联系策略或能力缺失触发的禁止操作黑名单)"]\n'
                "  }\n"
                "}\n"
                "禁止输出 `authorization_boundary_profile`、`permission_boundary`、旧字段 `allowed_actions`/`forbidden_actions`/`contact_policies`/`organizational_boundaries`，或任何额外顶层字段。"
            ),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "snapshot_version": snapshot_version,
        "q4_capability_boundary_profile": q4_capability_boundary_profile,
        "q4_permission_profile": q4_permission_profile,
        "rendered_q4_boundary": rendered_q4_boundary,
        "contact_policy": contact_policy,
        "tenant_scope": tenant_scope,
        "agent_trust_policy": agent_trust_policy,
        "q2_connected_agents": q2_connected_agents,
        "authorization_baseline": authorization_baseline,
        "functional_authorization_inputs": functional_authorization_inputs[:12],
        "identity_kernel": identity_kernel,
        "preprocessed_evidence": preprocessed_evidence,
        "question_driver_refs": question_driver_refs,
        "llm_temperature": 0.0,
        "llm_max_output_tokens": 2048,
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
