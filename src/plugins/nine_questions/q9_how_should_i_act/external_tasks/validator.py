from __future__ import annotations

from typing import Any


EXTERNAL_EXECUTOR_TYPES = {"agent", "cli", "mcp", "external_connector", "connector", "external_execution"}
INTERNAL_EXECUTOR_TYPES = {"internal", "internal_plugin", "cognitive_plugin", "reflection", "learning", "memory"}
ACTION_PLAN_FIELDS = {
    "current_action_plan",
    "method_selection",
    "required_resources",
    "assigned_role_profile",
    "risk_assessment",
    "on_failure_action",
    "estimated_confidence",
    "expected_results",
    "candidate_alternatives",
    "nine_question_mapping",
}
COGNITIVE_RESOURCE_TOKENS = (
    "analyzer",
    "clusterer",
    "cognitive",
    "learning",
    "memory",
    "reflection",
    "reranker",
    "sandbox",
    "selfmodel",
    "thought",
    "分析器",
    "聚类",
    "认知",
    "记忆",
    "反思",
    "学习",
    "沙盒",
)
EXTERNAL_RESOURCE_HINTS = (
    "agent",
    "audit",
    "cli",
    "cloud",
    "connector",
    "executor",
    "functional",
    "g12",
    "g30",
    "mcp",
    "plugin",
    "receipt",
    "safety",
    "service",
    "tool",
    "writer",
    "功能插件",
    "连接器",
    "命令行",
    "审计",
    "闸门",
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
INTERNAL_ENGINEERING_CODES = ("g31a", "g12", "g30")


class Q9ExternalTaskIsolationError(ValueError):
    error_code = "Q9_EXTERNAL_TASK_REFERENCES_INTERNAL_EXECUTOR"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _action_plan_text(action_plan: dict[str, Any]) -> str:
    values: list[str] = []
    for field in ACTION_PLAN_FIELDS:
        value = action_plan.get(field)
        if isinstance(value, list):
            values.extend(_text(item) for item in value)
        else:
            values.append(_text(value))
    return " ".join(item for item in values if item).lower()


def _validate_external_action_plan_schema(plan: dict[str, Any]) -> None:
    action_plan = plan.get("ActionPlan")
    if action_plan is None:
        return
    if not isinstance(action_plan, dict):
        raise Q9ExternalTaskIsolationError("Q9 ActionPlan must be an object")

    missing = sorted(ACTION_PLAN_FIELDS - set(action_plan))
    extra = sorted(set(action_plan) - ACTION_PLAN_FIELDS)
    if missing or extra:
        raise Q9ExternalTaskIsolationError(
            f"Q9 ActionPlan schema mismatch: missing={missing}, extra={extra}"
        )

    array_fields = (
        "current_action_plan",
        "required_resources",
        "expected_results",
        "candidate_alternatives",
        "nine_question_mapping",
    )
    for field in array_fields:
        if not isinstance(action_plan.get(field), list):
            raise Q9ExternalTaskIsolationError(f"Q9 ActionPlan.{field} must be an array")
    for field in ("method_selection", "assigned_role_profile", "risk_assessment", "on_failure_action"):
        if not isinstance(action_plan.get(field), str):
            raise Q9ExternalTaskIsolationError(f"Q9 ActionPlan.{field} must be a string")
    confidence = action_plan.get("estimated_confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0.0 <= float(confidence) <= 1.0:
        raise Q9ExternalTaskIsolationError("Q9 ActionPlan.estimated_confidence must be a number between 0.0 and 1.0")

    current_plan = _list(action_plan.get("current_action_plan"))
    resources = _list(action_plan.get("required_resources"))
    receipts = _list(action_plan.get("expected_results"))
    alternatives = _list(action_plan.get("candidate_alternatives"))
    mapping = _list(action_plan.get("nine_question_mapping"))
    if current_plan:
        for prefix in ("功能：", "执行方钦定：", "任务资源："):
            if not any(_text(item).startswith(prefix) for item in resources):
                raise Q9ExternalTaskIsolationError(f"Q9 ActionPlan.required_resources missing prefix {prefix}")
        if not [item for item in resources if _text(item)]:
            raise Q9ExternalTaskIsolationError("Q9 ActionPlan.required_resources cannot be empty")
        if not [item for item in receipts if _text(item)]:
            raise Q9ExternalTaskIsolationError("Q9 ActionPlan.expected_results cannot be empty")
        if not [item for item in alternatives if _text(item)]:
            raise Q9ExternalTaskIsolationError("Q9 ActionPlan.candidate_alternatives cannot be empty")
        joined_plan = " ".join(_text(item).lower() for item in [*current_plan, action_plan.get("method_selection"), action_plan.get("risk_assessment")])
        if "安全闸门" not in joined_plan or "云审计" not in joined_plan:
            raise Q9ExternalTaskIsolationError("Q9 external ActionPlan must explicitly route through safety gate and cloud audit")
        if any(code in _action_plan_text(action_plan) for code in INTERNAL_ENGINEERING_CODES):
            raise Q9ExternalTaskIsolationError("Q9 external ActionPlan must not expose internal engineering codes")
        if not _text(action_plan.get("assigned_role_profile")):
            raise Q9ExternalTaskIsolationError("Q9 ActionPlan.assigned_role_profile cannot be empty")
        if not _text(action_plan.get("on_failure_action")):
            raise Q9ExternalTaskIsolationError("Q9 ActionPlan.on_failure_action cannot be empty")
        if float(confidence) < 0.7 and "模拟沙盒" not in " ".join(_text(item) for item in current_plan):
            raise Q9ExternalTaskIsolationError("Q9 low-confidence external ActionPlan must include a simulation sandbox stage")
        mapping_text = " ".join(_text(item) for item in mapping)
        if "Q1" not in mapping_text or not any(token in mapping_text for token in ("静态资源", "绝对路径", "拓扑", "资源数据")):
            raise Q9ExternalTaskIsolationError("Q9 ActionPlan.nine_question_mapping must cite Q1 static-resource or topology evidence")

    joined = " ".join(_text(item).lower() for item in [*current_plan, action_plan.get("risk_assessment")])
    if any(token in joined for token in HIGH_RISK_TOKENS) and "云审计" not in joined:
        raise Q9ExternalTaskIsolationError("Q9 high-risk external actions must require cloud audit")

    cognitive_resources = [
        item for item in resources if any(token in _text(item).lower() for token in COGNITIVE_RESOURCE_TOKENS)
    ]
    if cognitive_resources:
        raise Q9ExternalTaskIsolationError(
            f"{Q9ExternalTaskIsolationError.error_code}: ActionPlan references cognitive resources: {cognitive_resources}"
        )

    non_external_resources = [
        item
        for item in resources
        if _text(item)
        and not _text(item).startswith(("功能：", "执行方钦定：", "任务资源："))
        and not any(token in _text(item).lower() for token in EXTERNAL_RESOURCE_HINTS)
    ]
    if non_external_resources:
        raise Q9ExternalTaskIsolationError(
            f"Q9 ActionPlan.required_resources contains non-external resources: {non_external_resources}"
        )

    receipt_hits = [item for item in receipts if "actionexecutionreceipt" in _text(item).lower()]
    if current_plan and not receipt_hits:
        raise Q9ExternalTaskIsolationError("Q9 ActionPlan must close with ActionExecutionReceipt evidence")


def validate_external_task_plan(plan: dict[str, Any]) -> dict[str, Any]:
    action_items = plan.get("action_items")
    if not isinstance(action_items, list):
        raise Q9ExternalTaskIsolationError("Q9 external plan must contain an action_items array")

    failures: list[dict[str, Any]] = []
    for index, item in enumerate(action_items):
        item = item if isinstance(item, dict) else {}
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        executor_type = _text(item.get("executor_type") or metadata.get("executor_type")).lower()
        task_scope = _text(item.get("task_scope") or metadata.get("task_scope")).lower()
        target_id = _text(item.get("target_id") or metadata.get("target_id"))
        capabilities = item.get("required_capabilities") or metadata.get("required_capabilities")
        has_capabilities = isinstance(capabilities, list) and bool([entry for entry in capabilities if _text(entry)])
        if (
            task_scope == "internal"
            or executor_type in INTERNAL_EXECUTOR_TYPES
            or executor_type not in EXTERNAL_EXECUTOR_TYPES
            or not target_id
            or not has_capabilities
            or metadata.get("functional_plugin_required") is not True
            or metadata.get("receipt_required") is not True
            or not isinstance(metadata.get("security_routing_requirements"), dict)
            or metadata.get("security_routing_requirements", {}).get("g12_safety_gate_required") is not True
        ):
            failures.append(
                {
                    "index": index,
                    "instruction": item.get("instruction"),
                    "executor_type": executor_type,
                    "task_scope": task_scope,
                    "target_id": target_id,
                    "has_capabilities": has_capabilities,
                    "functional_plugin_required": metadata.get("functional_plugin_required"),
                    "receipt_required": metadata.get("receipt_required"),
                }
            )

    if failures:
        raise Q9ExternalTaskIsolationError(
            f"{Q9ExternalTaskIsolationError.error_code}: external Q9 plan contains non-external executors: {failures}"
        )
    _validate_external_action_plan_schema(plan)
    return plan
