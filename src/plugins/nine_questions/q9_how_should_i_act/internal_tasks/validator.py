from __future__ import annotations

import re
from typing import Any


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
    "external api",
    "host file",
    "请求外部",
    "宿主文件",
    "发送请求",
    "修改文件",
    "执行脚本",
    "外部",
    "连接器",
    "命令行",
)
NEGATED_EXTERNAL_PATTERNS = (
    r"禁止[^。；;,.]*?(外部|连接器|命令行|执行脚本|发送请求|api|http|mcp|cli|connector|network)",
    r"不得[^。；;,.]*?(外部|连接器|命令行|执行脚本|发送请求|api|http|mcp|cli|connector|network)",
    r"不(?:触发|涉及|调用|执行|使用)[^。；;,.]*?(外部|连接器|命令行|执行脚本|发送请求|api|http|mcp|cli|connector|network)",
    r"无[^。；;,.]*?(外部|连接器|命令行|api|http|mcp|cli|connector|network)[^。；;,.]*?(副作用|调用|执行)",
    r"(avoid|without|no|never|do not|must not)[^.;,]*?(external|connector|cli|mcp|http|api call|network|send request|write file|workspace write)",
)
INTERNAL_ACTION_PLAN_FIELDS = {
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
}
INTERNAL_ACTION_STEP_FIELDS = {
    "step_description",
    "step_objective",
    "verification_method",
    "involved_modules",
}
INTERNAL_ALLOWED_RESOURCE_TOKENS = (
    "agenda",
    "b1",
    "b2",
    "b3",
    "b4",
    "b5",
    "b6",
    "b7",
    "b8",
    "brain",
    "cognitive",
    "engine",
    "evolution",
    "internal",
    "learning",
    "living",
    "memory",
    "budget",
    "reflection",
    "sandbox",
    "selfmodel",
    "thought",
    "内部",
    "认知",
    "脑内",
    "记忆",
    "反思",
    "学习",
    "进化",
    "沙盒",
)
SCHEDULER_OWNED_TOKENS = (
    "g31a",
    "g12",
    "g30",
    "subtaskrecord",
    "subtaskregistry",
    "subtaskscheduler",
    "taskassignmentrouter",
    "tasksplitter",
    "resourcematcher",
    "状态机",
    "子任务注册器",
    "子任务调度器",
    "任务拆分器",
    "资源匹配器",
)


class Q9InternalTaskIsolationError(ValueError):
    error_code = "Q9_INTERNAL_TASK_REFERENCES_EXTERNAL_CAPABILITY"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _contains_external_reference(value: Any) -> bool:
    text = _text(value).lower()
    if not text:
        return False
    if text.startswith(EXTERNAL_PREFIXES):
        return True
    if not any(token in text for token in EXTERNAL_SIDE_EFFECT_TOKENS):
        return False
    return not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in NEGATED_EXTERNAL_PATTERNS)


def _contains_scheduler_owned_reference(value: Any) -> bool:
    text = _text(value).lower()
    return any(token in text for token in SCHEDULER_OWNED_TOKENS)


def _field_values(action_plan: dict[str, Any], field: str) -> list[Any]:
    value = action_plan.get(field)
    return value if isinstance(value, list) else [value]


def _step_texts(action_plan: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for step in _list(action_plan.get("action_steps")):
        if isinstance(step, dict):
            texts.extend(_text(step.get(key)) for key in ("step_description", "step_objective", "verification_method"))
            texts.extend(_text(item) for item in _list(step.get("involved_modules")))
        else:
            texts.append(_text(step))
    return [item for item in texts if item]


def _validate_internal_action_plan_schema(plan: dict[str, Any]) -> None:
    action_plan = plan.get("InternalActionPlan")
    if action_plan is None:
        return
    if not isinstance(action_plan, dict):
        raise Q9InternalTaskIsolationError("Q9 InternalActionPlan must be an object")
    missing = sorted(INTERNAL_ACTION_PLAN_FIELDS - set(action_plan))
    extra = sorted(set(action_plan) - INTERNAL_ACTION_PLAN_FIELDS)
    if missing or extra:
        raise Q9InternalTaskIsolationError(
            f"Q9 InternalActionPlan schema mismatch: missing={missing}, extra={extra}"
        )

    array_fields = (
        "prohibited_actions_acknowledged",
        "required_resources",
        "action_steps",
        "success_criteria",
        "q_driver_refs",
    )
    for field in array_fields:
        if not isinstance(action_plan.get(field), list):
            raise Q9InternalTaskIsolationError(f"Q9 InternalActionPlan.{field} must be an array")
    for field in (
        "plan_objective",
        "execution_target",
        "fallback_plan",
        "identity_anchor",
        "cognitive_certainty",
    ):
        if not isinstance(action_plan.get(field), str):
            raise Q9InternalTaskIsolationError(f"Q9 InternalActionPlan.{field} must be a string")

    action_steps = _list(action_plan.get("action_steps"))
    resources = _list(action_plan.get("required_resources"))
    q_driver_refs = _list(action_plan.get("q_driver_refs"))
    for index, step in enumerate(action_steps):
        if not isinstance(step, dict):
            raise Q9InternalTaskIsolationError(f"Q9 InternalActionPlan.action_steps[{index}] must be an object")
        missing_step = sorted(INTERNAL_ACTION_STEP_FIELDS - set(step))
        extra_step = sorted(set(step) - INTERNAL_ACTION_STEP_FIELDS)
        if missing_step or extra_step:
            raise Q9InternalTaskIsolationError(
                f"Q9 InternalActionPlan.action_steps[{index}] schema mismatch: missing={missing_step}, extra={extra_step}"
            )
        for field in ("step_description", "step_objective", "verification_method"):
            if not isinstance(step.get(field), str) or not _text(step.get(field)):
                raise Q9InternalTaskIsolationError(f"Q9 InternalActionPlan.action_steps[{index}].{field} must be a non-empty string")
        if not isinstance(step.get("involved_modules"), list):
            raise Q9InternalTaskIsolationError(f"Q9 InternalActionPlan.action_steps[{index}].involved_modules must be an array")

    if action_steps:
        for field in ("plan_objective", "execution_target", "fallback_plan", "identity_anchor", "cognitive_certainty"):
            if not _text(action_plan.get(field)):
                raise Q9InternalTaskIsolationError(f"Q9 InternalActionPlan.{field} cannot be empty")
        if not [item for item in resources if _text(item)]:
            raise Q9InternalTaskIsolationError("Q9 InternalActionPlan.required_resources cannot be empty")
        if not [item for item in _list(action_plan.get("success_criteria")) if _text(item)]:
            raise Q9InternalTaskIsolationError("Q9 InternalActionPlan.success_criteria cannot be empty")
        refs_text = " ".join(_text(item) for item in q_driver_refs)
        if "Q1" not in refs_text or not any(token in refs_text for token in ("静态资源", "资源数据", "分布", "盲区")):
            raise Q9InternalTaskIsolationError("Q9 InternalActionPlan.q_driver_refs must cite Q1 static-resource evidence")
        if "Q8" not in refs_text:
            raise Q9InternalTaskIsolationError("Q9 InternalActionPlan.q_driver_refs must cite Q8 intent and constraints")

    external_hits = [
        {"field": field, "value": item}
        for field, values in (
            ("execution_target", [action_plan.get("execution_target")]),
            ("required_resources", _list(action_plan.get("required_resources"))),
            ("action_steps", _step_texts(action_plan)),
        )
        for item in values
        if _contains_external_reference(item)
    ]
    if external_hits:
        raise Q9InternalTaskIsolationError(
            f"{Q9InternalTaskIsolationError.error_code}: InternalActionPlan references external side effects: {external_hits}"
        )

    scheduler_hits = [
        {"field": field, "value": item}
        for field, values in (
            ("execution_target", [action_plan.get("execution_target")]),
            ("required_resources", _list(action_plan.get("required_resources"))),
            ("action_steps", _step_texts(action_plan)),
            ("success_criteria", _list(action_plan.get("success_criteria"))),
            ("fallback_plan", [action_plan.get("fallback_plan")]),
            ("q_driver_refs", _list(action_plan.get("q_driver_refs"))),
        )
        for item in values
        if _contains_scheduler_owned_reference(item)
    ]
    if scheduler_hits:
        raise Q9InternalTaskIsolationError(
            f"Q9 InternalActionPlan must not expose task-center internals or scheduler-owned records: {scheduler_hits}"
        )


def validate_internal_task_plan(plan: dict[str, Any]) -> dict[str, Any]:
    action_items = plan.get("action_items")
    if not isinstance(action_items, list):
        raise Q9InternalTaskIsolationError("Q9 internal plan must contain an action_items array")

    failures: list[dict[str, Any]] = []
    for index, item in enumerate(action_items):
        item = item if isinstance(item, dict) else {}
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        executor_type = _text(item.get("executor_type") or metadata.get("executor_type")).lower()
        target_id = _text(item.get("target_id") or metadata.get("target_id")).lower()
        task_scope = _text(item.get("task_scope") or metadata.get("task_scope")).lower()
        haystack = " ".join(
            _text(value).lower()
            for value in (
                item.get("instruction"),
                item.get("title"),
                item.get("target_id"),
                item.get("required_resource"),
                metadata.get("target_id"),
            )
        )
        if (
            task_scope == "external"
            or executor_type in EXTERNAL_EXECUTOR_TYPES
            or target_id.startswith(EXTERNAL_PREFIXES)
            or any(token in haystack for token in EXTERNAL_SIDE_EFFECT_TOKENS)
        ):
            failures.append(
                {
                    "index": index,
                    "instruction": item.get("instruction"),
                    "executor_type": executor_type,
                    "target_id": target_id,
                    "task_scope": task_scope,
                }
            )

    if failures:
        raise Q9InternalTaskIsolationError(
            f"{Q9InternalTaskIsolationError.error_code}: internal Q9 plan contains external references: {failures}"
        )
    _validate_internal_action_plan_schema(plan)
    return plan
