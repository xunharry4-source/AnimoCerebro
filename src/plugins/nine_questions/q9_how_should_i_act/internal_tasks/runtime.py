from __future__ import annotations

import logging
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
from .llm_request import build_q9_internal_llm_request
from .planner import build_internal_task_plan
from .system_prompt import build_q9_internal_system_prompt

logger = logging.getLogger(__name__)


def _q9_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _q9_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _q9_action_plan(raw_result: Any) -> dict[str, Any]:
    raw = _q9_dict(raw_result)
    action_plan = raw.get("InternalActionPlan") if isinstance(raw.get("InternalActionPlan"), dict) else {}
    if not isinstance(action_plan, dict) or not action_plan:
        raise RuntimeError("Q9 internal_tasks LLM output missing InternalActionPlan.")
    return action_plan


def _dedupe_list(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in items:
        key = str(json_safe_payload(item))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _merge_internal_action_plans(plans: list[dict[str, Any]]) -> dict[str, Any]:
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
        merged[field] = _dedupe_list(merged[field])
    return merged


def run_q9_internal_task_generation(
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
    self_model: dict[str, Any],
    reasoning_budget: dict[str, Any],
) -> dict[str, Any]:
    request_id = str(uuid4())
    scoped_trace_id = f"{trace_id}:q9-internal"
    module_run = start_module_run(
        q9_module_runs,
        "q9_internal_task_generation",
        source="plugins.nine_questions.q9.internal_tasks",
    )
    system_prompt = build_q9_internal_system_prompt()
    q2 = _q9_dict(q1_q8.get("q2"))
    q8 = _q9_dict(q1_q8.get("q8"))
    caller_context = build_caller_context(
        invocation_phase="nine_question_q9_internal_task_generation",
        source_module="q9_how_should_i_act.internal_tasks",
        question_ref="我应该如何行动:internal_tasks",
        question_driver_refs=context.get("question_driver_refs"),
        decision_id=decision_id,
        trace_id=scoped_trace_id,
    )
    q8_tasks = _q9_list(q8.get("internal_cognitive_tasks"))
    if not q8_tasks:
        raise RuntimeError("Q9 internal task generation requires at least one Q8 internal task.")
    llm_invocations: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    action_plans: list[dict[str, Any]] = []
    elapsed_total_ms = 0
    try:
        for task_index, q8_task in enumerate(q8_tasks):
            task_request_id = f"{request_id}:{task_index}"
            llm_request = build_q9_internal_llm_request(
                system_prompt=system_prompt,
                q8_internal_intents=[q8_task],
                q2_cognitive_capabilities_abstract=(
                    _q9_list(q2.get("cognitive_plugins"))
                    + _q9_list(q2.get("internal_cognitive_plugins"))
                    + _q9_list(q2.get("available_cognitive_tools"))
                ),
                brain_organ_states={
                    "self_model": self_model,
                    "reasoning_budget": reasoning_budget,
                },
                q1_environment=_q9_dict(q1_q8.get("q1")),
                q3_role_identity=_q9_dict(q1_q8.get("q3")),
                q4_capabilities_q7_redlines={
                    "q4": _q9_dict(q1_q8.get("q4")),
                    "q7": _q9_dict(q1_q8.get("q7")),
                },
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
                source="plugins.nine_questions.q9_how_should_i_act.internal_tasks",
                payload={"question_ref": "我应该如何行动:internal_tasks", **llm_input},
            )
            logger.info(
                "[Q9 INTERNAL LLM INPUT] trace_id=%s task_index=%s provider=%s payload=%s",
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
                target_question="q9.internal",
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
                module_id=f"q9_internal_task_generation_task_{task_index}",
                payload={
                    "q9_internal_llm_input": llm_input,
                    "q9_internal_llm_output": raw_result,
                    "q8_task_index": task_index,
                    "decomposition_mode": "single_q8_task_per_llm_call",
                },
                status="completed",
                output_kind="inference",
            )
            persist_q9_llm_task(
                db_path=context.get("nine_question_state_db_path"),
                session_id=session_id,
                task_scope="internal",
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
                source="plugins.nine_questions.q9_how_should_i_act.internal_tasks",
                payload={
                    "request_id": task_request_id,
                    "decision_id": decision_id,
                    "question_ref": "我应该如何行动:internal_tasks",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": raw_result,
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                    "elapsed_ms": elapsed_ms,
                },
            )
            logger.info(
                "[Q9 INTERNAL LLM OUTPUT] trace_id=%s task_index=%s provider=%s output=%s",
                scoped_trace_id,
                task_index,
                safe_provider_plugin_id(provider),
                json_safe_payload(raw_result),
            )
        action_plan = _merge_internal_action_plans(action_plans)
        plan = build_internal_task_plan(
            action_plan=action_plan,
            q1_q8=q1_q8,
            posture_baseline=posture_baseline,
            self_model=self_model,
            reasoning_budget=reasoning_budget,
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
                "Q1_Q8_Upstream_LLM_Outputs": upstream_llm_outputs,
                "Brain_Organ_States": {
                    "self_model": self_model,
                    "reasoning_budget": reasoning_budget,
                },
            },
        }
        raw_result = {
            "decomposition_mode": "single_q8_task_per_llm_call",
            "InternalActionPlan": action_plan,
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
            module_id="q9_internal_task_generation",
            payload={
                "q9_internal_llm_input": llm_input,
                "q9_internal_llm_output": raw_result,
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
            error_code="q9_internal_task_generation_failed",
            error_message=str(exc),
        )
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            source="plugins.nine_questions.q9_how_should_i_act.internal_tasks",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": "我应该如何行动:internal_tasks",
                "caller_context": caller_context.model_dump(mode="json"),
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q9 INTERNAL LLM ERROR] trace_id=%s error=%s", scoped_trace_id, exc)
        raise
