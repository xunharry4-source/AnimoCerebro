from __future__ import annotations

from typing import Any

from .context_builder import build_internal_task_context
from .validator import EXTERNAL_EXECUTOR_TYPES, EXTERNAL_PREFIXES, EXTERNAL_SIDE_EFFECT_TOKENS, validate_internal_task_plan


def _text(value: Any) -> str:
    return str(value or "").strip()


def _action_steps(action_plan: dict[str, Any]) -> list[dict[str, Any]]:
    steps = action_plan.get("action_steps")
    if isinstance(steps, list):
        normalized: list[dict[str, Any]] = []
        for step in steps:
            if isinstance(step, dict):
                normalized.append(
                    {
                        "step_description": _text(step.get("step_description")),
                        "step_objective": _text(step.get("step_objective")),
                        "verification_method": _text(step.get("verification_method")),
                        "involved_modules": [
                            _text(item)
                            for item in step.get("involved_modules", [])
                            if _text(item)
                        ]
                        if isinstance(step.get("involved_modules"), list)
                        else [],
                    }
                )
            elif _text(step):
                normalized.append(
                    {
                        "step_description": _text(step),
                        "step_objective": "完成该内部认知步骤的中间目标。",
                        "verification_method": "步骤输出非空且未触碰 Q8 禁令。",
                        "involved_modules": [],
                    }
                )
        return [step for step in normalized if _text(step.get("step_description"))]

    legacy_steps = action_plan.get("current_action_plan")
    if not isinstance(legacy_steps, list):
        return []
    return [
        {
            "step_description": _text(item),
            "step_objective": "完成该内部认知步骤的中间目标。",
            "verification_method": "步骤输出非空且未触碰 Q8 禁令。",
            "involved_modules": [],
        }
        for item in legacy_steps
        if _text(item)
    ]


def _is_external_instruction(instruction: str) -> bool:
    text = instruction.lower()
    return (
        any(text.startswith(prefix) or prefix in text for prefix in EXTERNAL_PREFIXES)
        or any(token in text for token in EXTERNAL_SIDE_EFFECT_TOKENS)
        or any(f" {executor} " in f" {text} " for executor in EXTERNAL_EXECUTOR_TYPES)
    )


def _internalize_step(step: dict[str, Any], *, index: int) -> dict[str, Any]:
    instruction = _text(step.get("step_description"))
    return {
        "action_id": f"q9-internal-action-{index}",
        "instruction": instruction,
        "task_scope": "internal",
        "executor_type": "internal",
        "target_id": "internal:q9_action_controller",
        "metadata": {
            "q9_action_index": index,
            "task_scope": "internal",
            "executor_type": "internal",
            "target_id": "internal:q9_action_controller",
            "execution_policy": "cognitive_only",
            "source_chain": "internal_q9",
            "step_objective": _text(step.get("step_objective")),
            "verification_method": _text(step.get("verification_method")),
            "involved_modules": [
                _text(item)
                for item in step.get("involved_modules", [])
                if _text(item)
            ]
            if isinstance(step.get("involved_modules"), list)
            else [],
        },
    }


def _internal_resources(context: dict[str, Any]) -> list[str]:
    capabilities: list[str] = []
    for capability in context.get("Q2_Cognitive_Capabilities_Abstract") or []:
        text = _text(capability.get("capability") if isinstance(capability, dict) else capability)
        if text:
            capabilities.append(text)
    function = capabilities[0] if capabilities else "internal_cognitive_analysis"
    executor = _designated_internal_executor(context, capabilities)
    resources = [
        function,
        executor,
        "内部工作记忆读取权限与认知推演预算",
    ]
    brain_states = context.get("Brain_Organ_States") if isinstance(context.get("Brain_Organ_States"), dict) else {}
    if brain_states.get("reasoning_budget"):
        resources.append("内部推理预算")
    return list(dict.fromkeys(resources))


def _designated_internal_executor(context: dict[str, Any], capabilities: list[str]) -> str:
    assets = [_text(item) for item in context.get("Q2_Assets") or [] if _text(item)]
    if not assets:
        return "内部认知分析能力"
    haystack = " ".join(capabilities).lower()
    for asset in assets:
        lowered = asset.lower()
        if "cluster" in haystack and ("cluster" in lowered or "聚类" in lowered):
            return asset
        if "sandbox" in haystack and ("sandbox" in lowered or "沙盒" in lowered or "thought" in lowered):
            return asset
        if "memory" in haystack and ("memory" in lowered or "记忆" in lowered):
            return asset
        if "learning" in haystack and ("learning" in lowered or "学习" in lowered):
            return asset
        if "reflection" in haystack and ("reflection" in lowered or "反思" in lowered):
            return asset
    return assets[0]


def _q1_static_resource_summary(context: dict[str, Any]) -> str:
    q1 = context.get("Q1_Environment") if isinstance(context.get("Q1_Environment"), dict) else {}
    static_resources = q1.get("internal_static_resources")
    notes = _text(q1.get("static_resource_notes"))
    distribution = _text(q1.get("static_resource_distribution"))
    if static_resources or notes or distribution:
        return f"Q1 静态资源依据：resources={static_resources or []}; distribution={distribution or '未说明'}; notes={notes or '未说明'}"
    return "Q1 静态资源依据不足：未发现完整的内部静态资源数据、分布特征或说明"


def _assigned_role_profile(context: dict[str, Any]) -> str:
    q3 = context.get("Q3_Role_IdentityKernel") if isinstance(context.get("Q3_Role_IdentityKernel"), dict) else {}
    anchors = q3.get("identity_anchors") if isinstance(q3.get("identity_anchors"), list) else []
    if anchors:
        return f"使用身份锚点 '{_text(anchors[0])}' 执行内部认知梳理"
    role = q3.get("role") if isinstance(q3.get("role"), dict) else {}
    role_name = _text(role.get("role_name") or role.get("name"))
    if role_name:
        return f"使用 '{role_name}' 角色子集执行内部认知梳理"
    return "使用'极致严谨的系统诊断员'角色子集执行内部逻辑梳理"


def _estimated_confidence(context: dict[str, Any]) -> float:
    q1 = context.get("Q1_Environment") if isinstance(context.get("Q1_Environment"), dict) else {}
    has_static_evidence = bool(
        q1.get("internal_static_resources")
        or q1.get("static_resource_distribution")
        or q1.get("static_resource_notes")
    )
    return 0.88 if has_static_evidence else 0.68


def _build_internal_action_plan(context: dict[str, Any], action_items: list[dict[str, Any]]) -> dict[str, Any]:
    if not action_items:
        return {
            "plan_objective": "",
            "prohibited_actions_acknowledged": [],
            "execution_target": "",
            "required_resources": [],
            "action_steps": [],
            "success_criteria": [],
            "fallback_plan": "",
            "identity_anchor": "",
            "cognitive_certainty": "",
            "q_driver_refs": [],
        }

    instructions = [_text(item.get("instruction")) for item in action_items if _text(item.get("instruction"))]
    q8_tasks = context.get("Q8_Tasks") if isinstance(context.get("Q8_Tasks"), list) else []
    plan_objective = _text(q8_tasks[0]) if q8_tasks else instructions[0]
    budget = context.get("Brain_Organ_States", {}).get("reasoning_budget", {})
    pressure = budget.get("budget_pressure") if isinstance(budget, dict) else None
    q1_summary = _q1_static_resource_summary(context)
    certainty = "高" if _estimated_confidence(context) >= 0.8 else "中"
    if pressure:
        certainty = f"{certainty}，受推理预算压力影响：{pressure}"
    involved_capabilities: list[str] = []
    for item in action_items:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        modules = metadata.get("involved_modules") if isinstance(metadata.get("involved_modules"), list) else []
        involved_capabilities.extend(_text(module) for module in modules if _text(module))
    constraints = context.get("constraints") if isinstance(context.get("constraints"), dict) else {}
    return {
        "plan_objective": plan_objective,
        "prohibited_actions_acknowledged": list(dict.fromkeys(
            _text(item)
            for item in constraints.get("forbidden_action_space", [])
            + constraints.get("absolute_red_lines", [])
            + constraints.get("non_bypassable_constraints", [])
            if _text(item)
        )),
        "execution_target": _designated_internal_executor(
            context,
            involved_capabilities or _internal_resources(context),
        ),
        "required_resources": _internal_resources(context),
        "action_steps": [
            {
                "step_description": instruction,
                "step_objective": _text(item.get("metadata", {}).get("step_objective")) or "完成该内部认知步骤的中间目标。",
                "verification_method": _text(item.get("metadata", {}).get("verification_method")) or "步骤输出非空且未触碰 Q8 禁令。",
                "involved_modules": item.get("metadata", {}).get("involved_modules", [])
                if isinstance(item.get("metadata", {}).get("involved_modules"), list)
                else [],
            }
            for item, instruction in zip(action_items, instructions)
        ],
        "success_criteria": [
            "成功生成与单一 Q8 内部任务一致的结构化认知步骤蓝图。",
            "每个步骤均包含说明、目标、验证方式和涉及模块，且不触碰 Q8 禁令。",
        ],
        "fallback_plan": "若上下文过大或分析失败，缩小为最高置信的一条内部认知步骤并保留失败原因供任务中心处理。",
        "identity_anchor": _assigned_role_profile(context),
        "cognitive_certainty": certainty,
        "q_driver_refs": [f"Q1依据：{q1_summary}", f"Q8驱动：承接单一内部任务 '{plan_objective}'"],
    }


def _normalize_internal_action_plan(action_plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if set(action_plan) == {
        "plan_objective",
        "prohibited_actions_acknowledged",
        "execution_target",
        "required_resources",
        "action_steps",
        "success_criteria",
        "fallback_plan",
        "identity_anchor",
        "cognitive_certainty",
        "q_driver_refs",
    }:
        return action_plan
    action_items = [
        _internalize_step(step, index=index)
        for index, step in enumerate(_action_steps(action_plan))
        if not _is_external_instruction(_text(step.get("step_description")))
    ]
    return _build_internal_action_plan(context, action_items)


def build_internal_task_plan(
    *,
    action_plan: dict[str, Any],
    q1_q8: dict[str, Any],
    posture_baseline: dict[str, Any],
    self_model: dict[str, Any],
    reasoning_budget: dict[str, Any],
) -> dict[str, Any]:
    context = build_internal_task_context(
        q1_q8=q1_q8,
        posture_baseline=posture_baseline,
        self_model=self_model,
        reasoning_budget=reasoning_budget,
    )
    normalized_action_plan = _normalize_internal_action_plan(action_plan, context)
    action_items = [
        _internalize_step(step, index=index)
        for index, step in enumerate(_action_steps(normalized_action_plan))
        if not _is_external_instruction(_text(step.get("step_description")))
    ]
    plan = {
        "planner": "q9_internal_task_handler",
        "context": context,
        "action_items": action_items,
        "InternalActionPlan": normalized_action_plan,
        "generated": len(action_items),
        "handling_rules": [
            "Q9 internal output is a ten-field InternalActionPlan blueprint",
            "The task center owns real task splitting, resource matching, registration, and scheduling",
            "Q9 may designate an internal executor from Q2 assets; the task center validates and binds the real runtime executor",
            "internal Q9 blueprints cannot reference Functional Plugins, CLI, MCP, external connectors, agents, network, or external execution",
        ],
    }
    return validate_internal_task_plan(plan)
