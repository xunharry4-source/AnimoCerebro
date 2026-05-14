from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping, Sequence

from zentex.tasks.decomposition.q9_blueprint_runtime import q9_g31a_verification_method


Q9_SUBTASK_SPLITTING_VALIDATION_SYSTEM_PROMPT = """
# [系统指令 / System Prompt: Zentex 认知蓝图与子任务合规验证器]

你是 Zentex 系统的【认知蓝图与子任务合规审计器】。
你的核心职责是：在研发测试或系统诊断阶段，严格审查 Q9（行动计划中枢）输出的行动蓝图（或其实例化后的子任务），判断其是否符合 Zentex 的“四维度数据契约”与“零信任防伪装红线”。

---

## 📥 一、 强制输入上下文规范 (Inputs)
你将接收并比对以下信息：
1. **[Original_Task_Intent]**: 原始的宏观任务意图（即 Q8 的决定）。
2. **[Subtasks_To_Verify]**: Q9 拆解出的子任务列表（包含步骤说明、目标、验证方式、执行模块）。
3. **[Available_Tools_Registry]**: 当前系统真实存在的合法执行方与认知工具清单（用于校验是否有捏造工具的幻觉）。

---

## 🔍 二、 核心验证维度与红线 (Validation Criteria)
你必须对传入的每一个子任务执行以下四维度的严苛审查。任何一项不达标，必须判定为不合规（invalid）：

1. **目标对齐校验 (Objective Alignment)**:
   - 审查子任务的 `step_objective`（或 `objective`）是否清晰？
   - 所有的子任务组合在一起，是否能闭环达成 [Original_Task_Intent]？是否存在目标漂移？
2. **执行方/模块真实性 (Execution Party Authenticity)**:
   - 审查 `involved_modules`（或 `required_resources`）。
   - 它请求的执行单元是否真实存在于 [Available_Tools_Registry] 中？绝对禁止捏造系统不存在的假执行方（如 Fake_Tool_99）。
3. **零信任物理验证契约 (Zero-Trust Verification Method)**:
   - 审查 `verification_method`（或 `acceptance_criteria`）。
   - **【最高红线】**：验证方式必须是**客观的物理证据**！例如：文件哈希值变化 (Hash)、修改时间 (mtime)、写后查询数据库记录 (read-after-write)、真实的退出码 (exit_code)。
   - 绝对拒绝诸如“观察是否成功”、“等待执行完毕”、“检查返回是否为 success”等主观、含糊或极易被执行单元伪装的假验证标准。
4. **颗粒度审查 (Granularity Check)**:
   - 任务是否被拆解到了最小可验证颗粒度？是否把过多的复杂操作糅合在了一个步骤中导致无法独立验证？

---

## 📤 三、 严格 JSON 格式与字段说明
你的输出必须是合法的纯 JSON 对象。根节点强制为 `SubtaskSplittingValidationReport`，必须精确包含以下字段：

1. **`is_compliant` (Boolean)**: 整体拆分结果是否完全合规。
2. **`compliance_score` (Float, 0.0 ~ 1.0)**: 整体拆分质量打分。
3. **`invalid_subtasks` (Array)**: 不合规的子任务审查明细列表。如果全部合规，请输出空数组 `[]`。
   - **`subtask_index` (Integer)**: 有问题的子任务序号。
   - **`violation_type` (Enum)**: 违规类型，必须是 `objective_drift` (目标漂移), `fake_execution_party` (捏造执行方), `fake_verification` (虚假验证方式), `granularity_too_large` (颗粒度过大) 之一。
   - **`violation_detail` (String)**: 详细指出哪里不合格，例如：“验证方式为‘检查命令行是否输出成功’，这违反了物理验证红线，应要求检查目标文件的修改时间”。
4. **`improvement_suggestion` (String)**: 给 Q9 提示词优化或系统修复的整体改进建议。

---

## 📝 四、 强制 JSON 输出结构范例

{
  "SubtaskSplittingValidationReport": {
    "is_compliant": false,
    "compliance_score": 0.65,
    "invalid_subtasks": [
      {
        "subtask_index": 2,
        "violation_type": "fake_verification",
        "violation_detail": "子任务2的 verification_method 仅要求'确认接口返回 HTTP 200'，这属于易被伪造的假验证。应要求调用 GET 接口重新读取刚才写入的记录（read-after-write）来作为真实物理证据。"
      },
      {
        "subtask_index": 3,
        "violation_type": "fake_execution_party",
        "violation_detail": "involved_modules 中捏造了名为 'Network_Firewall_Modifier' 的工具，该工具在当前 Available_Tools_Registry 中不存在，属于大模型幻觉。"
      }
    ],
    "improvement_suggestion": "Q9 存在虚构执行方和验证方式过于主观的问题，建议在 Q9 的 system prompt 中强化零信任取证要求，并注入真实的工具画像。"
  }
}
""".strip()


VIOLATION_TYPES = {
    "objective_drift",
    "fake_execution_party",
    "fake_verification",
    "granularity_too_large",
}

_OWNER_PREFIXES = ("internal:", "cli:", "mcp:", "agent:", "external_connector:", "connector:")
_EXTERNAL_PREFIXES = ("cli:", "mcp:", "agent:", "external_connector:", "connector:")
_STRONG_VERIFICATION_TOKENS = (
    "hash",
    "mtime",
    "read-after-write",
    "read after write",
    "exit_code",
    "stdout",
    "stderr",
    "sqlite",
    "select",
    "query",
    "readback",
    "checksum",
    "diff",
    "sha",
    "写后查询",
    "读回",
    "回查",
    "数据库",
    "退出码",
    "执行输出",
    "文件",
    "标记文件",
    "修改时间",
    "哈希",
    "行数",
    "记录",
    "回执",
    "审计",
)
_WEAK_VERIFICATION_PATTERNS = (
    r"观察.*成功",
    r"等待.*执行完毕",
    r"是否成功",
    r"返回\s*success",
    r"返回.*成功",
    r"检查.*success",
    r"确认.*成功$",
    r"http\s*200$",
    r"\b200\s*ok$",
)
_COMPOUND_ACTION_PATTERNS = (
    r"分析.*执行.*验证",
    r"读取.*修改.*验证",
    r"生成.*提交.*验证",
    r"检查.*修复.*验证",
    r"\bthen\b.*\bthen\b",
    r"\band\b.*\band\b",
    r"然后.*然后",
)


async def validate_q9_subtask_splitting_against_llm_output(
    *,
    original_task_intent: Any,
    q9_action_blueprint: Mapping[str, Any],
    child_tasks: Sequence[Any],
    available_tools_registry: Iterable[Mapping[str, Any]],
    plan_type: str,
    llm_service: Any = None,
) -> dict[str, Any]:
    """Validate physical G31A subtasks with LLM as the mandatory primary reviewer."""
    hard_guard_report = validate_q9_subtask_splitting_hard_guards(
        original_task_intent=original_task_intent,
        q9_action_blueprint=q9_action_blueprint,
        child_tasks=child_tasks,
        available_tools_registry=available_tools_registry,
        plan_type=plan_type,
    )
    llm_context = _build_llm_validation_context(
        original_task_intent=original_task_intent,
        q9_action_blueprint=q9_action_blueprint,
        child_tasks=child_tasks,
        available_tools_registry=available_tools_registry,
        plan_type=plan_type,
        hard_guard_report=hard_guard_report,
    )
    try:
        if llm_service is None:
            from zentex.llm import get_llm_service

            llm_service = get_llm_service()
        if llm_service is None or not callable(getattr(llm_service, "generate_json", None)):
            raise RuntimeError("LLM MANDATORY: q9 subtask splitting validation requires llm_service.generate_json")
        result = llm_service.generate_json(
            prompt=(
                "审查 Q9 ActionPlan 与已创建子任务是否合规。必须按系统提示词返回 "
                "SubtaskSplittingValidationReport JSON。规则硬红线报告只作为证据，"
                "不能替代你的审查结论；若硬红线发现 invalid，你的最终结论也必须 invalid。"
            ),
            context=llm_context,
            source_module="zentex.tasks.q9_subtask_splitting_validation",
            invocation_phase="q9_subtask_splitting_validation",
            system_prompt=Q9_SUBTASK_SPLITTING_VALIDATION_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=1800,
            metadata={"llm_mandatory": True, "q9_subtask_splitting_validation": True},
        )
        llm_payload = _normalize_llm_validation_payload(getattr(result, "output", result))
    except Exception as exc:
        return _llm_validation_failure_report(
            original_task_intent=original_task_intent,
            hard_guard_report=hard_guard_report,
            error=f"{type(exc).__name__}: {exc}",
        )
    return _merge_llm_and_hard_guard_reports(
        original_task_intent=original_task_intent,
        llm_report=llm_payload,
        hard_guard_report=hard_guard_report,
    )


def validate_q9_subtask_splitting_hard_guards(
    *,
    original_task_intent: Any,
    q9_action_blueprint: Mapping[str, Any],
    child_tasks: Sequence[Any],
    available_tools_registry: Iterable[Mapping[str, Any]],
    plan_type: str,
) -> dict[str, Any]:
    """Apply non-negotiable mechanical redlines; never substitutes for the LLM review."""
    blueprint = dict(q9_action_blueprint or {})
    expected_steps = _expected_step_records(blueprint, plan_type=plan_type)
    available_owner_refs = _available_owner_refs(available_tools_registry)
    expected_executor_refs = _expected_executor_refs(blueprint)
    invalid: list[dict[str, Any]] = []

    if not expected_steps:
        invalid.append(_violation(0, "granularity_too_large", "Q9 ActionPlan 没有可验证的 action_steps，任务中心无法证明子任务拆分符合 Q9 输出。"))
    if len(child_tasks) != len(expected_steps):
        invalid.append(
            _violation(
                -1,
                "objective_drift",
                f"子任务数量与 Q9 action_steps 不一致：expected={len(expected_steps)} actual={len(child_tasks)}。",
            )
        )

    for index, expected in enumerate(expected_steps):
        child = child_tasks[index] if index < len(child_tasks) else None
        if child is None:
            invalid.append(_violation(index, "objective_drift", f"缺少 Q9 action_steps[{index}] 对应的物理子任务。"))
            continue
        metadata = _task_metadata(child)
        contract = getattr(child, "contract", None)
        resource_gap_verified = _is_verified_resource_gap(child)
        actual_objective = _text(metadata.get("objective"))
        actual_step = _text(metadata.get("q9_blueprint_step"))
        actual_acceptance = [_text(item) for item in _list(metadata.get("acceptance_criteria")) if _text(item)]
        actual_resources = [_normalize_owner_ref(item) for item in _list(metadata.get("required_resources")) if _text(item)]

        if actual_objective != expected["objective"] or actual_step != expected["line"]:
            invalid.append(
                _violation(
                    index,
                    "objective_drift",
                    "子任务目标或蓝图步骤未严格继承 Q9 输出："
                    f"expected_objective={expected['objective']!r}, actual_objective={actual_objective!r}。",
                )
            )

        if not actual_acceptance:
            invalid.append(
                _violation(
                    index,
                    "fake_verification",
                    "子任务 acceptance_criteria 为空；G31A 必须写入基于任务状态、task_outcome 和执行证据读回的验收条件。",
                )
            )
        if expected.get("q9_verification_hint") and metadata.get("q9_verification_hint") != expected.get("q9_verification_hint"):
            invalid.append(
                _violation(
                    index,
                    "objective_drift",
                    "Q9 verification hint 未作为来源提示保留在 metadata.q9_verification_hint；"
                    "它只能用于蓝图追踪，不能作为任务中心验证方式。",
                )
            )
        if not _has_zero_trust_verification(child):
            invalid.append(
                _violation(
                    index,
                    "fake_verification",
                    "G31A 子任务验收条件或合同缺少客观物理证据，"
                    "必须使用 status=done、task_outcome.overall_passed、actual_outcome、hash/mtime/read-after-write/exit_code/真实读回等证据。",
                )
            )
        if not _has_enabled_real_verification_contract(child):
            invalid.append(
                _violation(
                    index,
                    "fake_verification",
                    "子任务 contract.verification 未启用或缺少真实 verifier；"
                    "不能只依赖 acceptance_criteria 文本冒充零信任验证。",
                )
            )

        if _is_granularity_too_large(expected["title"], expected["objective"]):
            invalid.append(
                _violation(
                    index,
                    "granularity_too_large",
                    "Q9 action step 混合了多个复杂动作，未达到最小可验证颗粒度。",
                )
            )

        owner_ref = _task_owner_ref(child)
        executor_type = _task_executor_type(child)
        if not owner_ref and resource_gap_verified:
            executor_type = executor_type or "resource_gap"
        if not owner_ref:
            invalid_execution_refs = _invalid_execution_refs(expected["required_resources"])
            detail = (
                "子任务未绑定真实执行方；"
                f"Q9 involved_modules 使用未知/非法执行方代码={invalid_execution_refs}。"
                "外部子任务必须绑定真实 Available_Tools_Registry 中的 "
                "cli:/mcp:/agent:/external_connector: owner_ref。"
                if invalid_execution_refs
                else f"子任务未绑定真实执行方；缺失执行方={_resource_gap_missing_resources(child)}。"
            )
            invalid.append(
                _violation(
                    index,
                    "fake_execution_party",
                    detail,
                )
            )
        elif plan_type == "external" and not owner_ref.startswith(_EXTERNAL_PREFIXES):
            invalid.append(_violation(index, "fake_execution_party", f"外部 Q9 子任务执行方不是 CLI/MCP/Agent/外接连接器：owner_ref={owner_ref!r}。"))
        elif plan_type == "internal" and not owner_ref.startswith("internal:"):
            invalid.append(_violation(index, "fake_execution_party", f"内部 Q9 子任务执行方不是内部功能插件：owner_ref={owner_ref!r}。"))
        if owner_ref and owner_ref not in available_owner_refs:
            invalid.append(_violation(index, "fake_execution_party", f"执行方 {owner_ref!r} 不存在于真实 Available_Tools_Registry。"))
        if owner_ref and expected_executor_refs and owner_ref not in expected_executor_refs:
            invalid.append(
                _violation(
                    index,
                    "fake_execution_party",
                    f"实际执行方 {owner_ref!r} 未匹配 Q9 指定执行方/模块 {sorted(expected_executor_refs)}。",
                )
            )
        if plan_type == "external" and _external_connector_owner_without_business_capability(child, expected["required_resources"]):
            invalid.append(
                _violation(
                    index,
                    "fake_execution_party",
                    "外部 connector 子任务只指定了连接器 owner，没有指定具体可执行业务 capability；"
                    "拆分结果必须包含该 connector registry 声明的具体业务能力，"
                    "不能把 external_connector:<id> 当成 runtime capability。",
                )
            )
        missing_dispatch_detail = _external_connector_dispatch_not_executable(child)
        if plan_type == "external" and missing_dispatch_detail:
            invalid.append(_violation(index, "fake_execution_party", missing_dispatch_detail))
        expected_resources = [_normalize_owner_ref(item) for item in expected["required_resources"]]
        if expected_resources and actual_resources != expected_resources:
            invalid.append(
                _violation(
                    index,
                    "fake_execution_party",
                    f"子任务 required_resources 未继承 Q9 involved_modules：expected={expected_resources}, actual={actual_resources}。",
                )
            )
        if not executor_type:
            invalid.append(_violation(index, "fake_execution_party", "子任务缺少真实 executor_type。"))

        expected_outcome = getattr(contract, "expected_outcome", {}) if contract is not None else {}
        if isinstance(expected_outcome, dict) and _text(expected_outcome.get("blueprint_step")) != expected["line"]:
            invalid.append(
                _violation(
                    index,
                    "objective_drift",
                    "子任务 contract.expected_outcome.blueprint_step 未绑定对应 Q9 action step。",
                )
            )

    compliance_score = max(0.0, 1.0 - (len(invalid) / max(1, len(expected_steps) * 4)))
    report = {
        "SubtaskSplittingValidationReport": {
            "is_compliant": not invalid,
            "compliance_score": round(compliance_score, 4),
            "invalid_subtasks": invalid,
            "improvement_suggestion": (
                "Q9 子任务拆分已通过目标、执行方、验证方式、颗粒度校验。"
                if not invalid
                else "Q9 子任务拆分未通过零信任合规校验；必须修正 Q9 prompt 或 G31A 拆分/绑定逻辑后重新生成，禁止降级为成功。"
            ),
            "original_task_intent": original_task_intent,
            "checked_dimensions": [
                "objective_alignment",
                "execution_party_authenticity",
                "zero_trust_verification_method",
                "granularity_check",
            ],
        }
    }
    return report


def _build_llm_validation_context(
    *,
    original_task_intent: Any,
    q9_action_blueprint: Mapping[str, Any],
    child_tasks: Sequence[Any],
    available_tools_registry: Iterable[Mapping[str, Any]],
    plan_type: str,
    hard_guard_report: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "Original_Task_Intent": _json_safe(original_task_intent),
        "Q9_Action_Blueprint": _json_safe(q9_action_blueprint),
        "Plan_Type": plan_type,
        "Subtasks_To_Verify": [_task_llm_payload(task, index=index) for index, task in enumerate(child_tasks)],
        "Available_Tools_Registry": _json_safe(list(available_tools_registry or [])),
        "Deterministic_Hard_Guard_Findings": _json_safe(hard_guard_report),
        "Hard_Redline_Policy": {
            "llm_is_primary_reviewer": True,
            "hard_guard_is_not_a_substitute_for_llm": True,
            "if_hard_guard_invalid_final_report_must_be_invalid": True,
            "no_rule_only_success_allowed": True,
        },
    }


def _task_llm_payload(task: Any, *, index: int) -> dict[str, Any]:
    metadata = _task_metadata(task)
    contract = getattr(task, "contract", None)
    assignment = getattr(task, "execution_assignment", {}) or {}
    return {
        "subtask_index": index,
        "task_id": getattr(task, "task_id", None),
        "title": getattr(task, "title", None),
        "description": getattr(task, "description", None),
        "status": _enum_value(getattr(task, "status", None)),
        "target_id": getattr(task, "target_id", None),
        "owner_ref": _task_owner_ref(task),
        "executor_type": _task_executor_type(task),
        "execution_assignment": _json_safe(assignment),
        "metadata": {
            "objective": metadata.get("objective"),
            "q9_blueprint_step": metadata.get("q9_blueprint_step"),
            "q9_verification_hint": metadata.get("q9_verification_hint"),
            "acceptance_criteria": metadata.get("acceptance_criteria"),
            "required_resources": metadata.get("required_resources"),
            "required_capabilities": metadata.get("required_capabilities"),
            "external_connector_id": metadata.get("external_connector_id"),
            "external_connector_capability": metadata.get("external_connector_capability"),
            "external_connector_arguments": metadata.get("external_connector_arguments"),
            "g31a_assignment": metadata.get("g31a_assignment"),
            "assignment_status": metadata.get("assignment_status"),
        },
        "contract": _contract_llm_payload(contract),
    }


def _contract_llm_payload(contract: Any) -> dict[str, Any]:
    if contract is None:
        return {}
    verification = getattr(contract, "verification", None)
    verifiers = getattr(verification, "verifiers", []) if verification is not None else []
    return {
        "expected_outcome": _json_safe(getattr(contract, "expected_outcome", {})),
        "verification_method": getattr(contract, "verification_method", None),
        "success_criteria": _json_safe(getattr(contract, "success_criteria", [])),
        "acceptance_conditions": _json_safe(getattr(contract, "acceptance_conditions", [])),
        "verification": {
            "enabled": getattr(verification, "enabled", None) if verification is not None else None,
            "strategy": _enum_value(getattr(verification, "strategy", None)) if verification is not None else None,
            "verifiers": [
                {
                    "name": getattr(verifier, "name", None),
                    "verifier_type": _enum_value(getattr(verifier, "verifier_type", None)),
                    "expected_status": getattr(verifier, "expected_status", None),
                    "rules": _json_safe(getattr(verifier, "rules", [])),
                }
                for verifier in verifiers
            ],
        },
    }


def _normalize_llm_validation_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned non-JSON validation payload: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"LLM returned non-object validation payload: {type(payload).__name__}")
    root = payload.get("SubtaskSplittingValidationReport", payload)
    if not isinstance(root, Mapping):
        raise ValueError("LLM validation payload missing object SubtaskSplittingValidationReport")
    invalid_subtasks = root.get("invalid_subtasks") if isinstance(root.get("invalid_subtasks"), list) else []
    return {
        "SubtaskSplittingValidationReport": {
            "is_compliant": root.get("is_compliant") is True,
            "compliance_score": _float_or_zero(root.get("compliance_score")),
            "invalid_subtasks": [
                _violation(
                    _int_or_default(item.get("subtask_index"), -1) if isinstance(item, Mapping) else -1,
                    _text(item.get("violation_type")) if isinstance(item, Mapping) else "objective_drift",
                    _text(item.get("violation_detail")) if isinstance(item, Mapping) else _text(item),
                )
                for item in invalid_subtasks
            ],
            "improvement_suggestion": _text(root.get("improvement_suggestion")),
            "checked_dimensions": root.get("checked_dimensions") if isinstance(root.get("checked_dimensions"), list) else [
                "objective_alignment",
                "execution_party_authenticity",
                "zero_trust_verification_method",
                "granularity_check",
            ],
        }
    }


def _merge_llm_and_hard_guard_reports(
    *,
    original_task_intent: Any,
    llm_report: Mapping[str, Any],
    hard_guard_report: Mapping[str, Any],
) -> dict[str, Any]:
    llm_payload = dict(llm_report.get("SubtaskSplittingValidationReport", {}))
    hard_payload = dict(hard_guard_report.get("SubtaskSplittingValidationReport", {}))
    llm_invalid = _list(llm_payload.get("invalid_subtasks"))
    hard_invalid = _list(hard_payload.get("invalid_subtasks"))
    invalid = _dedupe_violations([*llm_invalid, *hard_invalid])
    llm_compliant = llm_payload.get("is_compliant") is True
    hard_compliant = hard_payload.get("is_compliant") is True
    is_compliant = llm_compliant and hard_compliant and not invalid
    score = min(_float_or_zero(llm_payload.get("compliance_score")), _float_or_zero(hard_payload.get("compliance_score")))
    return {
        "SubtaskSplittingValidationReport": {
            "is_compliant": is_compliant,
            "compliance_score": score if is_compliant else min(score, max(0.0, 1.0 - (len(invalid) / max(1, len(invalid) + 4)))),
            "invalid_subtasks": invalid,
            "improvement_suggestion": (
                llm_payload.get("improvement_suggestion")
                or hard_payload.get("improvement_suggestion")
                or "Q9 子任务拆分需要 LLM 主审与硬红线同时通过。"
            ),
            "original_task_intent": original_task_intent,
            "checked_dimensions": [
                "objective_alignment",
                "execution_party_authenticity",
                "zero_trust_verification_method",
                "granularity_check",
            ],
            "validation_source": "llm_primary_with_deterministic_hard_guard",
            "llm_required": True,
            "llm_validation_report": _json_safe(llm_report),
            "deterministic_hard_guard_report": _json_safe(hard_guard_report),
        }
    }


def _llm_validation_failure_report(
    *,
    original_task_intent: Any,
    hard_guard_report: Mapping[str, Any],
    error: str,
) -> dict[str, Any]:
    hard_payload = dict(hard_guard_report.get("SubtaskSplittingValidationReport", {}))
    invalid = [
        *_list(hard_payload.get("invalid_subtasks")),
        _violation(-1, "fake_verification", f"Q9 子任务拆分合规审查必须调用 LLM；LLM 审查失败，禁止规则替代 LLM：{error}"),
    ]
    return {
        "SubtaskSplittingValidationReport": {
            "is_compliant": False,
            "compliance_score": 0.0,
            "invalid_subtasks": _dedupe_violations(invalid),
            "improvement_suggestion": "修复 LLM 服务或调用链后重新执行 Q9 子任务拆分；禁止用 deterministic rule gate 冒充 LLM 审查。",
            "original_task_intent": original_task_intent,
            "checked_dimensions": [
                "objective_alignment",
                "execution_party_authenticity",
                "zero_trust_verification_method",
                "granularity_check",
            ],
            "validation_source": "llm_required_failed_closed",
            "llm_required": True,
            "llm_error": error,
            "deterministic_hard_guard_report": _json_safe(hard_guard_report),
        }
    }


def _dedupe_violations(items: Sequence[Any]) -> list[dict[str, Any]]:
    seen: set[tuple[int, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        violation = _violation(
            _int_or_default(item.get("subtask_index"), -1),
            _text(item.get("violation_type")),
            _text(item.get("violation_detail")),
        )
        key = (violation["subtask_index"], violation["violation_type"], violation["violation_detail"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(violation)
    return deduped


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, Mapping):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(item) for item in value]
        return _enum_value(value) or _text(value)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _expected_step_records(blueprint: Mapping[str, Any], *, plan_type: str) -> list[dict[str, Any]]:
    steps = blueprint.get("action_steps") or blueprint.get("current_action_plan") or []
    if not isinstance(steps, list):
        return []
    records: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            text = _text(step)
            if text:
                records.append(
                    {
                        "title": text,
                        "objective": text,
                        "verification_method": q9_g31a_verification_method(plan_type),
                        "q9_verification_hint": "",
                        "required_resources": [],
                        "line": text,
                    }
                )
            continue
        title = _text(step.get("step_description"))
        objective = _text(step.get("step_objective"))
        q9_verification_hint = _text(step.get("verification_method"))
        resources = [_text(item) for item in _list(step.get("involved_modules")) if _text(item)]
        line = "；".join(
            item
            for item in (
                f"步骤说明：{title}",
                f"步骤目标：{objective}",
                f"Q9检查提示：{q9_verification_hint}",
                f"涉及模块：{', '.join(resources)}" if resources else "",
            )
            if item and not item.endswith("：")
        )
        if line:
            records.append(
                {
                    "title": title or line,
                    "objective": objective or line,
                    "verification_method": q9_g31a_verification_method(plan_type),
                    "q9_verification_hint": q9_verification_hint,
                    "required_resources": resources,
                    "line": line,
                }
            )
    return records


def _available_owner_refs(registry: Iterable[Mapping[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for item in registry or []:
        ref = _normalize_owner_ref(item.get("owner_ref") or item.get("executor_id") or "")
        if ref:
            refs.add(ref)
    return refs


def _expected_executor_refs(blueprint: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    for value in [blueprint.get("execution_target"), *list(blueprint.get("required_resources") or [])]:
        text = _text(value)
        if text.startswith(("执行方钦定：", "执行方钦定:")):
            text = text.split(":", 1)[-1].strip() if "执行方钦定:" in text else text.split("：", 1)[-1].strip()
        ref = _normalize_owner_ref(text)
        if ref.startswith(_OWNER_PREFIXES):
            refs.add(ref)
    for step in _list(blueprint.get("action_steps")):
        if not isinstance(step, dict):
            continue
        for module in _list(step.get("involved_modules")):
            ref = _normalize_owner_ref(module)
            if ref.startswith(_OWNER_PREFIXES):
                refs.add(ref)
    return refs


def _task_metadata(task: Any) -> dict[str, Any]:
    metadata = getattr(task, "metadata", {}) or {}
    return metadata if isinstance(metadata, dict) else {}


def _task_owner_ref(task: Any) -> str:
    metadata = _task_metadata(task)
    assignment = getattr(task, "execution_assignment", {}) or {}
    if isinstance(assignment, dict):
        owner = _normalize_owner_ref(assignment.get("executor_id") or assignment.get("owner_ref") or "")
        if owner:
            return owner
    g31a_assignment = metadata.get("g31a_assignment") if isinstance(metadata.get("g31a_assignment"), dict) else {}
    return _normalize_owner_ref(
        metadata.get("owner_ref")
        or g31a_assignment.get("owner_ref")
        or getattr(task, "target_id", "")
        or metadata.get("target_id")
        or metadata.get("q9_proposed_owner_ref")
        or ""
    )


def _task_executor_type(task: Any) -> str:
    metadata = _task_metadata(task)
    assignment = getattr(task, "execution_assignment", {}) or {}
    if isinstance(assignment, dict) and _text(assignment.get("executor_type")):
        return _text(assignment.get("executor_type"))
    return _text(metadata.get("executor_type"))


def _has_zero_trust_verification(task: Any) -> bool:
    values: list[Any] = []
    metadata = _task_metadata(task)
    values.extend(_list(metadata.get("acceptance_criteria")))
    contract = getattr(task, "contract", None)
    if contract is not None:
        values.append(getattr(contract, "verification_method", ""))
        values.extend(_list(getattr(contract, "success_criteria", [])))
        values.extend(_list(getattr(contract, "acceptance_conditions", [])))
        expected_outcome = getattr(contract, "expected_outcome", {})
        if isinstance(expected_outcome, Mapping):
            values.extend(expected_outcome.values())
    return any(_is_zero_trust_verification(_text(value)) for value in values)


def _has_enabled_real_verification_contract(task: Any) -> bool:
    contract = getattr(task, "contract", None)
    verification = getattr(contract, "verification", None) if contract is not None else None
    if verification is None or getattr(verification, "enabled", False) is not True:
        return False
    verifiers = getattr(verification, "verifiers", []) or []
    if not verifiers:
        return False
    for verifier in verifiers:
        verifier_type = getattr(verifier, "verifier_type", "")
        verifier_type_value = getattr(verifier_type, "value", verifier_type)
        if _text(verifier_type_value) in {"rule_based", "log_audit", "automated_test", "combined"}:
            return True
    return False


def _is_verified_resource_gap(task: Any) -> bool:
    metadata = _task_metadata(task)
    assignment = metadata.get("g31a_assignment")
    if not isinstance(assignment, Mapping):
        return False
    evidence = assignment.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    return (
        metadata.get("assignment_status") == "suspended_resource_gap"
        and assignment.get("status") == "suspended_resource_gap"
        and _list(assignment.get("missing_resources"))
        and evidence.get("matched_by") == "G31A.ResourceMatcher"
        and isinstance(evidence.get("candidate_counts_by_registry"), Mapping)
        and isinstance(evidence.get("candidate_owners"), list)
    )


def _resource_gap_missing_resources(task: Any) -> list[Any]:
    metadata = _task_metadata(task)
    assignment = metadata.get("g31a_assignment")
    if isinstance(assignment, Mapping):
        resources = _list(assignment.get("missing_resources"))
        if resources:
            return resources
    return _list(metadata.get("required_resources"))


def _external_connector_owner_without_business_capability(task: Any, expected_resources: Sequence[Any]) -> bool:
    metadata = _task_metadata(task)
    executor_type = _task_executor_type(task)
    owner_ref = _task_owner_ref(task)
    if executor_type != "external_connector" and not owner_ref.startswith("external_connector:"):
        return False
    capabilities = [_text(item) for item in _list(metadata.get("required_capabilities")) if _text(item)]
    capability = _text(metadata.get("external_connector_capability") or metadata.get("connector_capability"))
    if capability and not _normalize_owner_ref(capability).startswith(_OWNER_PREFIXES):
        return False
    if any(item and not _normalize_owner_ref(item).startswith(_OWNER_PREFIXES) for item in capabilities):
        return False
    resources = [_text(item) for item in expected_resources if _text(item)]
    return bool(resources) and all(_normalize_owner_ref(item).startswith(("external_connector:", "connector:")) for item in resources)


def _external_connector_dispatch_not_executable(task: Any) -> str:
    metadata = _task_metadata(task)
    executor_type = _task_executor_type(task)
    owner_ref = _task_owner_ref(task)
    if executor_type != "external_connector" and not owner_ref.startswith("external_connector:"):
        return ""
    connector_id = _text(metadata.get("external_connector_id") or metadata.get("connector_id"))
    capability = _text(metadata.get("external_connector_capability") or metadata.get("connector_capability") or metadata.get("capability"))
    if not connector_id:
        return "外部 connector 子任务缺少 external_connector_id，worker 无法构造真实 dispatch。"
    if not capability or _normalize_owner_ref(capability).startswith(_OWNER_PREFIXES):
        return "外部 connector 子任务缺少具体 external_connector_capability，worker 无法调用 registry 声明的业务能力。"
    arguments = metadata.get("external_connector_arguments")
    if arguments is None:
        arguments = metadata.get("connector_arguments")
    if arguments is None:
        arguments = metadata.get("arguments")
    if capability in {"mongodb_csv_inspect", "mongodb_csv_import"}:
        if not isinstance(arguments, Mapping):
            return f"{capability} 子任务缺少 external_connector_arguments，无法定位真实 CSV 输入。"
        has_csv_input = any(_text(arguments.get(key)) for key in ("csv_path", "directory_path"))
        csv_paths = arguments.get("csv_paths")
        if isinstance(csv_paths, list) and any(_text(item) for item in csv_paths):
            has_csv_input = True
        if not has_csv_input:
            return f"{capability} 子任务缺少 csv_path/csv_paths/directory_path，不能调度到真实 CSV 检查连接器。"
    return ""


def _invalid_execution_refs(values: list[Any]) -> list[str]:
    invalid: list[str] = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        ref = _normalize_owner_ref(text)
        if not ref.startswith(_OWNER_PREFIXES):
            invalid.append(text)
    return invalid


def _is_zero_trust_verification(value: str) -> bool:
    text = _text(value).lower()
    if not text:
        return False
    has_strong_evidence = any(token in text for token in _STRONG_VERIFICATION_TOKENS)
    has_weak_only_signal = any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _WEAK_VERIFICATION_PATTERNS)
    return has_strong_evidence and not (has_weak_only_signal and not has_strong_evidence)


def _is_granularity_too_large(*parts: str) -> bool:
    text = " ".join(_text(part) for part in parts)
    if not text:
        return True
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _COMPOUND_ACTION_PATTERNS):
        return True
    return text.count("并") >= 3 or text.count("、") >= 6


def _violation(index: int, violation_type: str, detail: str) -> dict[str, Any]:
    if violation_type not in VIOLATION_TYPES:
        violation_type = "objective_drift"
    return {
        "subtask_index": index,
        "violation_type": violation_type,
        "violation_detail": detail,
    }


def _normalize_owner_ref(value: Any) -> str:
    text = _text(value)
    if text.startswith("connector:"):
        return f"external_connector:{text.split(':', 1)[1]}"
    return text


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()
