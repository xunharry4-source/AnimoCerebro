from __future__ import annotations

import logging
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

from zentex.common.nine_questions_shared import (
    build_caller_context,
    fail_module_run,
    finish_module_run,
    json_safe_payload,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    safe_provider_plugin_id,
    start_module_run,
)
from zentex.nine_questions.q8_q9_boundary import validate_goal_inheritance

from ..llm_output_table import persist_q9_llm_task
from .llm_request import build_q9_external_llm_request
from .planner import build_external_task_plan
from .system_prompt import build_q9_external_system_prompt

logger = logging.getLogger(__name__)


def _q9_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _q9_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _q9_action_plan(raw_result: Any) -> dict[str, Any]:
    raw = _q9_dict(raw_result)
    action_plan = raw.get("ExternalActionPlan") if isinstance(raw.get("ExternalActionPlan"), dict) else {}
    if not isinstance(action_plan, dict) or not action_plan:
        raise RuntimeError("Q9 external_tasks LLM output missing ExternalActionPlan.")
    _validate_external_action_plan_contract(action_plan)
    return action_plan


def _validate_external_action_plan_contract(action_plan: dict[str, Any]) -> None:
    required = {
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
    missing = sorted(required - set(action_plan))
    if missing:
        raise RuntimeError(f"Q9 external_tasks ExternalActionPlan missing required fields: {missing}")
    for field in ("prohibited_actions_acknowledged", "required_resources", "action_steps", "success_criteria", "q_driver_refs"):
        if not isinstance(action_plan.get(field), list):
            raise RuntimeError(f"Q9 external_tasks ExternalActionPlan field {field} must be a list.")
    step_fields = {"step_description", "step_objective", "verification_method", "involved_modules"}
    for index, step in enumerate(action_plan["action_steps"]):
        if not isinstance(step, dict):
            raise RuntimeError(f"Q9 external_tasks action_steps[{index}] must be an object.")
        extra = sorted(set(step) - step_fields)
        missing_step = sorted(step_fields - set(step))
        if extra or missing_step:
            raise RuntimeError(
                "Q9 external_tasks action_steps[%s] must contain only %s; extra=%s missing=%s"
                % (index, sorted(step_fields), extra, missing_step)
            )
        if not isinstance(step.get("involved_modules"), list):
            raise RuntimeError(f"Q9 external_tasks action_steps[{index}].involved_modules must be a list.")


def _dedupe_external_values(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for value in values:
        if isinstance(value, str) and not value.strip():
            continue
        key = json.dumps(json_safe_payload(value), ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _action_step_text(step: Any) -> str:
    if isinstance(step, dict):
        modules = step.get("involved_modules")
        modules_text = ", ".join(str(item).strip() for item in modules if str(item or "").strip()) if isinstance(modules, list) else ""
        return "；".join(
            item
            for item in (
                f"步骤说明：{str(step.get('step_description') or '').strip()}",
                f"步骤目标：{str(step.get('step_objective') or '').strip()}",
                f"验证方式：{str(step.get('verification_method') or '').strip()}",
                f"涉及模块：{modules_text}" if modules_text else "",
            )
            if item and not item.endswith("：")
        )
    return str(step or "").strip()


def _merge_external_action_plans(plans: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
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
    if not plans:
        return merged

    list_fields = (
        "prohibited_actions_acknowledged",
        "required_resources",
        "action_steps",
        "success_criteria",
        "q_driver_refs",
    )
    string_fields = ("plan_objective", "execution_target", "fallback_plan", "identity_anchor", "cognitive_certainty")
    for plan in plans:
        for field in list_fields:
            values = plan.get(field)
            if isinstance(values, list):
                merged[field].extend(item for item in values if str(item or "").strip())
        for field in string_fields:
            text = str(plan.get(field) or "").strip()
            if text:
                merged[field] = "\n".join(item for item in (merged[field], text) if item)
    for field in list_fields:
        merged[field] = _dedupe_external_values(merged[field])
    return merged


def _legacy_action_plan_for_task_handler(external_plan: dict[str, Any]) -> dict[str, Any]:
    resources = [
        "功能：外部功能插件、CLI、MCP 或协作 Agent 的受审计执行能力",
        f"执行方钦定：{external_plan.get('execution_target') or 'external_execution:unresolved'}",
        "任务资源：安全闸门、云审计链路、ActionExecutionReceipt 回执通道与目标宿主权限",
    ]
    resources.extend(
        str(item).strip()
        for item in external_plan.get("required_resources", [])
        if str(item or "").strip()
    )
    return {
        "current_action_plan": [
            f"external_execution: {_action_step_text(step)}"
            for step in external_plan.get("action_steps", [])
            if _action_step_text(step)
        ],
        "method_selection": "按 ExternalActionPlan 单任务蓝图交由任务中心做真实资源绑定和执行调度。",
        "required_resources": resources,
        "assigned_role_profile": str(external_plan.get("identity_anchor") or ""),
        "risk_assessment": str(external_plan.get("cognitive_certainty") or ""),
        "on_failure_action": str(external_plan.get("fallback_plan") or ""),
        "estimated_confidence": 0.8,
        "expected_results": list(external_plan.get("success_criteria") or []),
        "candidate_alternatives": [str(external_plan.get("fallback_plan") or "")],
        "nine_question_mapping": list(external_plan.get("q_driver_refs") or []),
    }


def run_q9_external_task_generation(
    *,
    context: dict[str, Any],
    provider: Any,
    transcript_store: Any,
    session_id: str,
    turn_id: str,
    trace_id: str,
    decision_id: str,
    q9_module_runs: list[dict[str, Any]],
    q1_q8: dict[str, Any],
    upstream_llm_outputs: dict[str, Any],
    posture_baseline: dict[str, Any],
) -> dict[str, Any]:
    request_id = str(uuid4())
    scoped_trace_id = f"{trace_id}:q9-external"
    module_run = start_module_run(
        q9_module_runs,
        "q9_external_task_generation",
        source="plugins.nine_questions.q9.external_tasks",
    )
    system_prompt = build_q9_external_system_prompt()
    q2 = _q9_dict(q1_q8.get("q2"))
    q8 = _q9_dict(q1_q8.get("q8"))
    caller_context = build_caller_context(
        invocation_phase="nine_question_q9_external_task_generation",
        source_module="q9_how_should_i_act.external_tasks",
        question_ref="我应该如何行动:external_tasks",
        question_driver_refs=context.get("question_driver_refs"),
        decision_id=decision_id,
        trace_id=scoped_trace_id,
    )
    q8_tasks = _q9_list(q8.get("external_execution_tasks"))
    if not q8_tasks:
        raise RuntimeError("Q9 external task generation requires at least one Q8 external task.")
    llm_invocations: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    action_plans: list[dict[str, Any]] = []
    elapsed_total_ms = 0
    try:
        for task_index, q8_task in enumerate(q8_tasks):
            task_request_id = f"{request_id}:{task_index}"
            llm_request = build_q9_external_llm_request(
                system_prompt=system_prompt,
                q8_external_tasks=[q8_task],
                q2_functional_plugins=(
                    _q9_list(q2.get("functional_plugins"))
                    + _q9_list(q2.get("available_execution_tools"))
                    + _q9_list(q2.get("external_agents"))
                ),
                q4_external_capabilities=_q9_dict(q1_q8.get("q4")),
                q5_authorization=_q9_dict(q1_q8.get("q5")),
                q7_redlines=_q9_dict(q1_q8.get("q7")),
                q1_environment=_q9_dict(q1_q8.get("q1")),
                q3_role_identity=_q9_dict(q1_q8.get("q3")),
            )
            model_context = dict(llm_request["model_context"])
            model_context["Q1_Q8_Upstream_LLM_Outputs"] = upstream_llm_outputs
            model_context["Q8_Task_Decomposition_Mode"] = "single_q8_task_per_llm_call"
            model_context["Q8_Task_Index"] = task_index
            model_context["max_json_repair_attempts"] = 3
            model_context["temperature"] = 0
            llm_input = {
                "request_id": task_request_id,
                "decision_id": decision_id,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "system_prompt": llm_request["system_prompt"],
                "prompt": llm_request["prompt"],
                "context": model_context,
            }
            record_model_invoked(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=scoped_trace_id,
                source="plugins.nine_questions.q9_how_should_i_act.external_tasks",
                payload={"question_ref": "我应该如何行动:external_tasks", **llm_input},
            )
            logger.info(
                "[Q9 EXTERNAL LLM INPUT] trace_id=%s task_index=%s provider=%s payload=%s",
                scoped_trace_id,
                task_index,
                safe_provider_plugin_id(provider),
                json_safe_payload(llm_input),
            )
            started = perf_counter()
            raw_result = provider.generate_json(
                prompt=f"{llm_request['system_prompt']}\n\n{llm_request['prompt']}",
                context=model_context,
                caller_context=caller_context,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
            elapsed_total_ms += elapsed_ms
            action_plan = _q9_action_plan(raw_result)
            validate_goal_inheritance(
                source_question="q8",
                target_question="q9.external",
                expected_goal=q8_task,
                actual_goal=action_plan.get("plan_objective"),
            )
            raw_results.append(raw_result)
            action_plans.append(action_plan)
            llm_invocations.append(
                {
                    "task_index": task_index,
                    "q8_task": q8_task,
                    "llm_input": llm_input,
                    "llm_output": raw_result,
                    "elapsed_ms": elapsed_ms,
                }
            )
            persist_question_module_output(
                context,
                question_id="q9",
                module_id=f"q9_external_task_generation_task_{task_index}",
                payload={
                    "q9_external_llm_input": llm_input,
                    "q9_external_llm_output": raw_result,
                    "q8_task_index": task_index,
                    "decomposition_mode": "single_q8_task_per_llm_call",
                },
                status="completed",
                output_kind="inference",
            )
            persist_q9_llm_task(
                db_path=context.get("nine_question_state_db_path"),
                session_id=session_id,
                task_scope="external",
                task_index=task_index,
                q8_task=q8_task,
                llm_input=llm_input,
                llm_output=raw_result,
                trace_id=scoped_trace_id,
                provider_name=safe_provider_plugin_id(provider),
                model=str(getattr(provider, "last_model_name", None) or ""),
                token_usage=getattr(provider, "last_token_usage", None),
                elapsed_ms=elapsed_ms,
            )
            record_model_completed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=scoped_trace_id,
                source="plugins.nine_questions.q9_how_should_i_act.external_tasks",
                payload={
                    "request_id": task_request_id,
                    "decision_id": decision_id,
                    "question_ref": "我应该如何行动:external_tasks",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": raw_result,
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                    "elapsed_ms": elapsed_ms,
                },
            )
            logger.info(
                "[Q9 EXTERNAL LLM OUTPUT] trace_id=%s task_index=%s provider=%s output=%s",
                scoped_trace_id,
                task_index,
                safe_provider_plugin_id(provider),
                json_safe_payload(raw_result),
            )
        action_plan = _merge_external_action_plans(action_plans)
        plan = build_external_task_plan(
            action_plan=_legacy_action_plan_for_task_handler(action_plan),
            q1_q8=q1_q8,
            posture_baseline=posture_baseline,
        )
        finish_module_run(module_run)
        raw_response = json_safe_payload(getattr(provider, "last_raw_response", None))
        token_usage = json_safe_payload(getattr(provider, "last_token_usage", None))
        model_name = json_safe_payload(getattr(provider, "last_model_name", None))
        llm_input = {
            "request_id": request_id,
            "decision_id": decision_id,
            "provider_plugin_id": safe_provider_plugin_id(provider),
            "caller_context": caller_context.model_dump(mode="json"),
            "decomposition_mode": "single_q8_task_per_llm_call",
            "invocations": [item["llm_input"] for item in llm_invocations],
            "context": {
                "Q8_Tasks": q8_tasks,
                "Q2_Assets": (
                    _q9_list(q2.get("functional_plugins"))
                    + _q9_list(q2.get("available_execution_tools"))
                    + _q9_list(q2.get("external_agents"))
                ),
                "Q1_Q8_Upstream_LLM_Outputs": upstream_llm_outputs,
            },
        }
        raw_result = {
            "decomposition_mode": "single_q8_task_per_llm_call",
            "ExternalActionPlan": action_plan,
            "task_outputs": raw_results,
        }
        llm_trace_payload = {
            "request_id": request_id,
            "decision_id": decision_id,
            "provider_name": safe_provider_plugin_id(provider),
            "model": model_name,
            "source_module": caller_context.source_module,
            "invocation_phase": caller_context.invocation_phase,
            "question_driver_refs": caller_context.question_driver_refs,
            "context_data": llm_input["context"],
            "raw_response": raw_result,
            "token_usage": token_usage if isinstance(token_usage, dict) else {},
            "elapsed_ms": elapsed_total_ms,
        }
        persist_question_module_output(
            context,
            question_id="q9",
            module_id="q9_external_task_generation",
            payload={
                "q9_external_llm_input": llm_input,
                "q9_external_llm_output": raw_result,
            },
            status=str(module_run.get("status") or "completed"),
            output_kind="inference",
        )
        return {
            "action_plan": action_plan,
            "plan": plan,
            "llm_input": llm_input,
            "llm_output": raw_result,
            "llm_trace_payload": llm_trace_payload,
            "module_run": module_run,
        }
    except Exception as exc:
        fail_module_run(
            module_run,
            error_code="q9_external_task_generation_failed",
            error_message=str(exc),
        )
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            source="plugins.nine_questions.q9_how_should_i_act.external_tasks",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": "我应该如何行动:external_tasks",
                "caller_context": caller_context.model_dump(mode="json"),
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q9 EXTERNAL LLM ERROR] trace_id=%s error=%s", scoped_trace_id, exc)
        raise
