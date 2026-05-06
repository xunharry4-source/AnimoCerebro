from __future__ import annotations

import re
from typing import Any

from .context_builder import build_external_task_context
from .validator import validate_external_task_plan


EXTERNAL_EXECUTOR_TYPES = {"agent", "cli", "mcp", "external_connector", "connector", "external_execution"}
EXTERNAL_PREFIXES = ("agent:", "cli:", "mcp:", "external_connector:", "connector:", "external_execution:")
EXTERNAL_SIDE_EFFECT_TOKENS = (
    "agent:",
    "api call",
    "cli:",
    "connector:",
    "external execution",
    "external_executor",
    "external_tool",
    "external_connector:",
    "http",
    "mcp:",
    "network",
    "send request",
    "workspace write",
    "write file",
    "外部",
    "连接器",
    "命令行",
)
HIGH_RISK_TOKENS = (
    "delete",
    "file",
    "git push",
    "http",
    "modify",
    "network",
    "post",
    "reload",
    "request",
    "restart",
    "send",
    "write",
    "删除",
    "发送",
    "发网",
    "请求",
    "修改",
    "写入",
    "重启",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _action_steps(action_plan: dict[str, Any]) -> list[str]:
    steps = action_plan.get("current_action_plan") or action_plan.get("action_steps")
    if not isinstance(steps, list):
        return []
    normalized: list[str] = []
    for item in steps:
        if isinstance(item, dict):
            modules = item.get("involved_modules")
            modules_text = ", ".join(_text(module) for module in modules if _text(module)) if isinstance(modules, list) else ""
            text = "；".join(
                part
                for part in (
                    f"步骤说明：{_text(item.get('step_description'))}",
                    f"步骤目标：{_text(item.get('step_objective'))}",
                    f"验证方式：{_text(item.get('verification_method'))}",
                    f"涉及模块：{modules_text}" if modules_text else "",
                )
                if part and not part.endswith("：")
            )
        else:
            text = _text(item)
        if text:
            normalized.append(text)
    return normalized


def _resource_hints(action_plan: dict[str, Any]) -> list[str]:
    resources = action_plan.get("required_resources")
    if not isinstance(resources, list):
        return []
    return [_text(item) for item in resources if _text(item)]


def _is_external_instruction(instruction: str) -> bool:
    text = instruction.lower()
    return (
        any(text.startswith(prefix) or prefix in text for prefix in EXTERNAL_PREFIXES)
        or any(token in text for token in EXTERNAL_SIDE_EFFECT_TOKENS)
        or any(f" {executor} " in f" {text} " for executor in EXTERNAL_EXECUTOR_TYPES)
    )


def _first_prefixed_value(text: str, prefix: str) -> str:
    match = re.search(rf"{re.escape(prefix)}[A-Za-z0-9_.:-]+", text)
    return match.group(0) if match else ""


def _derive_executor(instruction: str, resource_hints: list[str]) -> tuple[str, str, list[str], dict[str, Any]]:
    search_text = " ".join([instruction, *resource_hints]).lower()
    metadata: dict[str, Any] = {}
    if "cli:" in search_text or " cli " in f" {search_text} " or "命令行" in search_text:
        target = _first_prefixed_value(search_text, "cli:") or "cli:unspecified"
        tool = target.removeprefix("cli:")
        metadata["cli_tool_name"] = tool
        return "cli", target, ["external.cli", *([f"cli.{tool}"] if tool and tool != "unspecified" else [])], metadata
    if "mcp:" in search_text or " mcp " in f" {search_text} ":
        target = _first_prefixed_value(search_text, "mcp:") or "mcp:unspecified"
        parts = target.split(":", 2)
        server = parts[1] if len(parts) >= 2 else ""
        tool = parts[2] if len(parts) == 3 else ""
        metadata.update({"mcp_server_id": server, "mcp_tool_name": tool})
        capabilities = ["external.mcp"]
        if server and tool:
            capabilities.append(f"mcp.{server}.{tool}")
        return "mcp", target, capabilities, metadata
    if "external_connector:" in search_text or "connector:" in search_text or "连接器" in search_text:
        target = (
            _first_prefixed_value(search_text, "external_connector:")
            or _first_prefixed_value(search_text, "connector:")
            or "external_connector:unspecified"
        )
        connector = target.split(":", 1)[1] if ":" in target else ""
        metadata["external_connector_id"] = connector
        return "external_connector", target, ["external.external_connector"], metadata
    if "agent:" in search_text or " agent " in f" {search_text} ":
        target = _first_prefixed_value(search_text, "agent:") or "agent:unspecified"
        agent_id = target.removeprefix("agent:")
        metadata["agent_id"] = agent_id
        return "agent", target, ["external.agent", *([f"agent.{agent_id}"] if agent_id and agent_id != "unspecified" else [])], metadata
    return "external_execution", "external_execution:unresolved", ["external.execution"], metadata


def _externalize_instruction(
    instruction: str,
    *,
    index: int,
    resource_hints: list[str],
) -> dict[str, Any]:
    executor_type, target_id, capabilities, executor_metadata = _derive_executor(instruction, resource_hints)
    capabilities = list(dict.fromkeys(item for item in capabilities if _text(item)))
    g30_required = _requires_g30([instruction, *resource_hints])
    return {
        "action_id": f"q9-external-action-{index}",
        "instruction": instruction,
        "task_scope": "external",
        "executor_type": executor_type,
        "target_id": target_id,
        "required_capabilities": capabilities,
        "metadata": {
            **executor_metadata,
            "q9_action_index": index,
            "task_scope": "external",
            "executor_type": executor_type,
            "external_executor_type": executor_type,
            "target_id": target_id,
            "required_capabilities": capabilities,
            "functional_plugin_required": True,
            "receipt_required": True,
            "security_routing_requirements": {
                "g12_safety_gate_required": True,
                "g30_cloud_audit_required": g30_required,
            },
            "expected_receipt_type": "ActionExecutionReceipt",
            "safety_gate_required": True,
            "g12_safety_gate_required": True,
            "g30_cloud_audit_required": g30_required,
            "source_chain": "external_q9",
        },
    }


def _requires_g30(values: list[str]) -> bool:
    text = " ".join(_text(item).lower() for item in values)
    return any(token in text for token in HIGH_RISK_TOKENS)


def _functional_resources(context: dict[str, Any], action_items: list[dict[str, Any]]) -> list[str]:
    assets = [_text(item) for item in context.get("Q2_Functional_Assets") or [] if _text(item)]
    designated = _designated_external_executor(context, action_items)
    if designated not in assets and assets:
        designated = assets[0]
    resources = [
        "功能：外部功能插件、CLI、MCP 或协作 Agent 的受审计执行能力",
        f"执行方钦定：{designated}",
        "任务资源：安全闸门、云审计链路、ActionExecutionReceipt 回执通道与目标宿主权限",
    ]
    return list(dict.fromkeys(item for item in resources if _text(item)))


def _designated_external_executor(context: dict[str, Any], action_items: list[dict[str, Any]]) -> str:
    assets = [_text(item) for item in context.get("Q2_Functional_Assets") or [] if _text(item)]
    if not assets:
        return "external_execution:unresolved"
    targets = [_text(item.get("target_id")) for item in action_items if isinstance(item, dict) and _text(item.get("target_id"))]
    for target in targets:
        if target in assets:
            return target
        target_tail = target.split(":", 1)[1] if ":" in target else target
        for asset in assets:
            if asset == target_tail or asset.endswith(f":{target_tail}"):
                return asset
    haystack = " ".join([*targets, *(_text(item.get("instruction")) for item in action_items if isinstance(item, dict))]).lower()
    for asset in assets:
        lowered = asset.lower()
        if "cli" in haystack and ("cli" in lowered or lowered.startswith("cli:")):
            return asset
        if "mcp" in haystack and ("mcp" in lowered or lowered.startswith("mcp:")):
            return asset
        if "agent" in haystack and ("agent" in lowered or lowered.startswith("agent:")):
            return asset
        if ("github" in haystack or "repository" in haystack or "代码库" in haystack) and "github" in lowered:
            return asset
        if ("file" in haystack or "写入" in haystack or "文件" in haystack) and ("file" in lowered or "writer" in lowered or "cli" in lowered):
            return asset
    return assets[0]


def _q1_static_resource_summary(context: dict[str, Any]) -> str:
    q1 = context.get("Q1_Environment") if isinstance(context.get("Q1_Environment"), dict) else {}
    static_resources = q1.get("internal_static_resources")
    paths = q1.get("static_resource_absolute_paths")
    topology = _text(q1.get("workspace_topology"))
    notes = _text(q1.get("static_resource_notes"))
    if static_resources or paths or topology or notes:
        return f"Q1 静态资源依据：resources={static_resources or []}; paths={paths or []}; topology={topology or '未说明'}; notes={notes or '未说明'}"
    return "Q1 静态资源依据不足：未发现完整的内部静态资源数据、绝对路径或拓扑说明"


def _assigned_role_profile(context: dict[str, Any]) -> str:
    q3 = context.get("Q3_Role_IdentityKernel") if isinstance(context.get("Q3_Role_IdentityKernel"), dict) else {}
    anchors = q3.get("identity_anchors") if isinstance(q3.get("identity_anchors"), list) else []
    if anchors:
        return f"使用身份锚点 '{_text(anchors[0])}' 执行外部干预调度"
    role = q3.get("role") if isinstance(q3.get("role"), dict) else {}
    role_name = _text(role.get("role_name") or role.get("name"))
    if role_name:
        return f"使用 '{role_name}' 角色子集执行外部宿主环境干预"
    return "使用'保守型高级运维工程师'角色进行外部宿主环境干预"


def _estimated_confidence(context: dict[str, Any]) -> float:
    q1 = context.get("Q1_Environment") if isinstance(context.get("Q1_Environment"), dict) else {}
    has_static_evidence = bool(
        q1.get("internal_static_resources")
        or q1.get("static_resource_absolute_paths")
        or q1.get("workspace_topology")
        or q1.get("static_resource_notes")
    )
    return 0.75 if has_static_evidence else 0.66


def _build_external_action_plan(
    *,
    context: dict[str, Any],
    action_items: list[dict[str, Any]],
    resource_hints: list[str],
) -> dict[str, Any]:
    if not action_items:
        return {
            "current_action_plan": [],
            "method_selection": "",
            "required_resources": [],
            "assigned_role_profile": "",
            "risk_assessment": "",
            "on_failure_action": "",
            "estimated_confidence": 0.0,
            "expected_results": [],
            "candidate_alternatives": [],
            "nine_question_mapping": [],
        }

    instructions = [_text(item.get("instruction")) for item in action_items if _text(item.get("instruction"))]
    g30_required = any(_requires_g30([instruction, *resource_hints]) for instruction in instructions)
    q1_summary = _q1_static_resource_summary(context)
    confidence = _estimated_confidence(context)
    simulation_steps = ["步骤：因认知确定度低于 0.7，先触发模拟沙盒验证外部干预风险，再提交审批。"] if confidence < 0.7 else []
    return {
        "current_action_plan": [
            f"目标：基于 {q1_summary}，承接 Q8 外部执行意图并形成受审计干涉计划：{instruction}"
            for index, instruction in enumerate(instructions)
        ]
        + simulation_steps
        + [
            "步骤：将每个外部动作意图提交至安全闸门与云审计，审批前不得执行。",
            "步骤：审批通过后，由任务中心触发钦定的功能插件、CLI、MCP 连接器或外部 Agent。",
            "步骤：等待 ActionExecutionReceipt 并绑定到 Q9 外部行动轨迹后才允许闭环。",
        ],
        "method_selection": (
            "选择外部执行与协作调度路径，是因为该任务会干涉宿主环境，必须通过安全闸门与云审计审批、"
            "由任务中心真实拆解和调度，并以 ActionExecutionReceipt 作为闭环证据。"
        ),
        "required_resources": _functional_resources(context, action_items),
        "assigned_role_profile": _assigned_role_profile(context),
        "risk_assessment": (
            "外部副作用风险受 Q7 红线、安全闸门、云审计和强制回执验收约束。"
            f"{'涉及中高风险外部动作，必须启用云审计。' if g30_required else '当前仍需声明安全闸门与云审计路由以防旁路执行。'}"
        ),
        "on_failure_action": (
            "当任务被安全闸门阻断、云审计拒绝或物理执行失败时，立即撤销临时变更，"
            "释放写锁，保留失败回执，并触发人工干预请求。"
        ),
        "estimated_confidence": confidence,
        "expected_results": [
            "成功条件：ActionExecutionReceipt 必须包含 executor_id、action_id、status、started_at、completed_at 与不可变输出证据。",
            "成功条件：ActionExecutionReceipt 必须证明外部执行方返回成功或类型化失败，且未绕过安全闸门与云审计。",
        ],
        "candidate_alternatives": [
            "若安全闸门或云审计拒绝动作意图，降级为生成人工审查建议，不执行外部动作。",
            "若外部执行方超时或权限不足，保持任务阻塞并请求新的授权功能插件路径。",
        ],
        "nine_question_mapping": [
            f"Q1依据：{q1_summary}；Q8外部任务：{instruction}；受 Q4 外部能力与 Q7 红线约束。"
            for instruction in instructions
        ],
    }


def build_external_task_plan(
    *,
    action_plan: dict[str, Any],
    q1_q8: dict[str, Any],
    posture_baseline: dict[str, Any],
) -> dict[str, Any]:
    context = build_external_task_context(q1_q8=q1_q8, posture_baseline=posture_baseline)
    resources = _resource_hints(action_plan)
    action_items = [
        _externalize_instruction(instruction, index=index, resource_hints=resources)
        for index, instruction in enumerate(_action_steps(action_plan))
        if _is_external_instruction(instruction)
    ]
    plan = {
        "planner": "q9_external_task_handler",
        "context": context,
        "action_items": action_items,
        "ActionPlan": _build_external_action_plan(
            context=context,
            action_items=action_items,
            resource_hints=resources,
        ),
        "generated": len(action_items),
        "follow_up_events": [
            "route external action through Q5/Q7 safety gates before dispatch",
            "record external action receipt before treating Q9 action as completed",
        ],
    }
    return validate_external_task_plan(plan)
