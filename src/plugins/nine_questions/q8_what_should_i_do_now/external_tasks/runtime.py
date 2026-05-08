from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.llm_request import (
    build_q8_external_staged_llm_request,
)
from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.system_prompt import (
    build_q8_external_system_prompt,
)
from plugins.nine_questions.q8_what_should_i_do_now.modules import (
    merge_string_lists,
    normalize_q8_external_execution_tasks,
    normalize_q8_inference_payload,
)
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

logger = logging.getLogger(__name__)


def _log(message: str) -> None:
    logger.info("[Q8ExternalTasks] %s", message)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    normalized: list[Any] = []
    for item in value:
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            compact = {
                str(key): _text(val)
                for key, val in item.items()
                if val not in (None, "", [], {})
            }
            if compact:
                normalized.append(compact)
        else:
            normalized.append(_text(item))
    return normalized


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _candidate(title: Any, *, source_question: str, reason: str, required_capability: str = "") -> dict[str, str]:
    return {
        "title": _text(title),
        "source_question": source_question,
        "reason": _text(reason),
        "required_capability": _text(required_capability),
    }


def _q2_functional_plugins(question_snapshot: dict[str, Any]) -> list[str]:
    q2 = _dict(question_snapshot.get("q2"))
    return merge_string_lists(
        merge_string_lists(
            _list(q2.get("functional_capabilities")),
            _list(q2.get("available_execution_tools")),
        ),
        _list(q2.get("functional_plugins")),
    )


def _q2_cognitive_plugins(question_snapshot: dict[str, Any]) -> list[str]:
    q2 = _dict(question_snapshot.get("q2"))
    return merge_string_lists(
        merge_string_lists(
            _list(q2.get("cognitive_capabilities")),
            _list(q2.get("available_cognitive_tools")),
        ),
        _list(q2.get("cognitive_plugins")),
    )


def _external_capability_permission_missing(q4_payload: dict[str, Any], q3_payload: dict[str, Any]) -> bool:
    q4_text = _json(q4_payload).lower()
    explicit_missing_markers = (
        "缺乏外部功能执行权限",
        "缺少外部功能执行权限",
        "无外部功能执行权限",
        "no external execution",
        "lacks external execution",
        "external execution unavailable",
        "external execution disabled",
    )
    if any(marker in q4_text for marker in explicit_missing_markers):
        return True
    permission_profile = _dict(q4_payload.get("permission_profile"))
    if permission_profile.get("is_read_only") is True:
        return True
    return not bool(_list(q3_payload.get("available_execution_tools")))


def _external_capability_payload(question_snapshot: dict[str, Any]) -> dict[str, Any]:
    q3 = _dict(question_snapshot.get("q3"))
    q4 = _dict(question_snapshot.get("q4"))
    return {
        "available_execution_tools": _list(q3.get("available_execution_tools")),
        "actionable_space": _list(q4.get("actionable_space")),
        "executable_strategies": _list(q4.get("executable_strategies")),
        "capability_upper_limits": _list(q4.get("capability_upper_limits")),
        "permission_profile": _dict(q4.get("permission_profile")),
        "external_execution_permission_missing": _external_capability_permission_missing(q4, q3),
    }


def _redline_payload(question_snapshot: dict[str, Any]) -> dict[str, Any]:
    q6 = _dict(question_snapshot.get("q6"))
    q7 = _dict(question_snapshot.get("q7"))
    return {
        "absolute_red_lines": _list(q6.get("absolute_red_lines")),
        "prohibited_strategies": _list(q6.get("prohibited_strategies")),
        "current_red_line_hits": _list(q7.get("current_red_line_hits")),
        "rejected_operation_records": _list(q7.get("rejected_operation_records")),
        "non_bypassable_constraints": _list(q7.get("non_bypassable_constraints")),
    }


def _derive_external_candidate_tasks(
    question_snapshot: dict[str, Any],
    priority_baseline: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    q3 = _dict(question_snapshot.get("q3"))
    q4 = _dict(question_snapshot.get("q4"))
    q4_permission = _dict(q4.get("permission_profile"))

    for task in _list(priority_baseline.get("immediate_tasks")):
        candidates.append(
            _candidate(
                task,
                source_question="q8_priority_baseline",
                reason="Derived from the deterministic Q8 priority baseline.",
            )
        )
    for task in _list(q4.get("actionable_space")):
        candidates.append(
            _candidate(
                task,
                source_question="q4",
                reason="Allowed by the current capability boundary.",
                required_capability=task,
            )
        )
    for task in _list(q4.get("executable_strategies")):
        candidates.append(
            _candidate(
                task,
                source_question="q4",
                reason="Executable strategy reported by Q4.",
                required_capability=task,
            )
        )
    for task in _list(q3.get("available_execution_tools")):
        candidates.append(
            _candidate(
                f"use available execution tool: {task}",
                source_question="q3",
                reason="Execution tool is available in the current resource inventory.",
                required_capability=task,
            )
        )
    for entries in normalized_task_state.values():
        for entry in entries:
            title = entry.get("title") if isinstance(entry, dict) else entry
            candidates.append(
                _candidate(
                    title,
                    source_question="task_state",
                    reason="Existing persistent task state contains this active task.",
                )
            )
    if q4_permission.get("is_read_only"):
        candidates.append(
            _candidate(
                "prepare read-only analysis and request confirmation before side effects",
                source_question="q4",
                reason="Q4 permission profile indicates read-only mode.",
                required_capability="read_only_analysis",
            )
        )

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        title = item.get("title", "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        deduped.append(item)
    return deduped


def _filter_external_candidate_tasks(
    candidate_tasks: list[dict[str, str]],
    question_snapshot: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    q5 = _dict(question_snapshot.get("q5"))
    q6 = _dict(question_snapshot.get("q6"))
    q7 = _dict(question_snapshot.get("q7"))
    forbidden = [
        str(item).lower()
        for item in (
            _list(q5.get("forbidden_action_space"))
            + _list(q5.get("forbidden_actions"))
            + _list(q5.get("unauthorized_actions"))
            + _list(q6.get("absolute_red_lines"))
            + _list(q6.get("prohibited_strategies"))
            + _list(q7.get("current_red_line_hits"))
            + _list(q7.get("non_bypassable_constraints"))
        )
        if str(item).strip()
    ]
    allowed: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    for item in candidate_tasks:
        title = item.get("title", "")
        matched = next((rule for rule in forbidden if rule and rule in title.lower()), "")
        if matched:
            blocked.append({"title": title, "reason": f"Conflicts with permission/redline constraint: {matched}", "blocked_by": matched})
        else:
            allowed.append({"title": title, "reason": item.get("reason", ""), "priority_hint": item.get("source_question", "")})
    return allowed, blocked


def _model_name(provider: Any, context: dict[str, Any]) -> Any:
    return json_safe_payload(
        getattr(provider, "last_model_name", None)
        or context.get("llm_model")
        or context.get("model")
        or context.get("model_name")
    )


def run_q8_external_task_generation(
    *,
    context: dict[str, Any],
    provider: Any,
    transcript_store: Any,
    module_runs: list[dict[str, Any]],
    question_snapshot: dict[str, Any],
    priority_baseline: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]],
    request_timeout_seconds: float,
    session_id: str,
    turn_id: str,
    trace_id: str,
    decision_id: str,
    request_id: str,
) -> dict[str, Any]:
    module_run = start_module_run(
        module_runs,
        "q8_external_task_generation",
        source="plugins.nine_questions.q8.external_tasks",
    )
    started = perf_counter()
    scoped_trace_id = f"{trace_id}:external"
    scoped_decision_id = f"{decision_id}:external"
    caller_context = build_caller_context(
        invocation_phase="nine_question_q8_external_decision",
        source_module="q8_what_should_i_do_now.external_tasks",
        question_ref="我现在应该做什么",
        question_driver_refs=context.get("question_driver_refs"),
        decision_id=scoped_decision_id,
        trace_id=scoped_trace_id,
    )

    try:
        _log("START build external Q8 LLM parameters")
        q2_functional_plugins = _q2_functional_plugins(question_snapshot)
        q2_cognitive_plugins = _q2_cognitive_plugins(question_snapshot)
        q4_external_capabilities = _external_capability_payload(question_snapshot)
        q7_redlines = _redline_payload(question_snapshot)
        candidate_tasks = _derive_external_candidate_tasks(
            question_snapshot,
            priority_baseline,
            normalized_task_state,
        )
        allowed_tasks, blocked_tasks = _filter_external_candidate_tasks(candidate_tasks, question_snapshot)
        request_payload = build_q8_external_staged_llm_request(
            system_prompt=build_q8_external_system_prompt(),
            priority_baseline=priority_baseline,
            allowed_tasks=allowed_tasks,
            blocked_tasks=blocked_tasks,
            q1_llm_output=question_snapshot.get("q1", {}),
            q7_snapshot=question_snapshot.get("q7", {}),
            normalized_task_state=normalized_task_state,
            request_timeout_seconds=request_timeout_seconds,
            q2_functional_plugins=q2_functional_plugins,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q4_external_capabilities=q4_external_capabilities,
            q7_redlines=q7_redlines,
            q1_q7_snapshot=question_snapshot,
        )
        reasoning = {
            "effective_request_scope": "external",
            "candidate_count": len(candidate_tasks),
            "allowed_count": len(allowed_tasks),
            "blocked_count": len(blocked_tasks),
            "candidate_sample": candidate_tasks,
            "allowed_sample": allowed_tasks,
            "blocked_sample": blocked_tasks,
            "q2_functional_plugins": q2_functional_plugins,
            "q4_external_capabilities": q4_external_capabilities,
        }
        _log(f"END build external Q8 LLM parameters candidates={len(candidate_tasks)}")

        model_name = _model_name(provider, context)
        llm_input = {
            "system_prompt": request_payload["system_prompt"],
            "prompt": request_payload["prompt"],
            "context": request_payload["context"],
            "caller_context": caller_context.model_dump(mode="json"),
        }
        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            source="plugins.nine_questions.q8_what_should_i_do_now.external_tasks",
            payload={
                "q8_external_llm_input": llm_input,
            },
        )
        logger.error(
            "[Q8 EXTERNAL LLM INPUT] trace_id=%s provider=%s model=%s payload=%s",
            scoped_trace_id,
            safe_provider_plugin_id(provider),
            model_name or "unknown",
            _json(llm_input),
        )
        from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.instructor_contract import (
            generate_external_objective_profile_with_instructor_contract,
        )

        raw_result = generate_external_objective_profile_with_instructor_contract(
            provider,
            prompt=request_payload["prompt"],
            context=request_payload["context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q8",
                "scope": "external",
                "output_schema": "ExternalObjectiveProfileRoot",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        logger.error(
            "[Q8 EXTERNAL LLM OUTPUT] trace_id=%s provider=%s model=%s output=%s",
            scoped_trace_id,
            safe_provider_plugin_id(provider),
            _model_name(provider, context) or model_name or "unknown",
            _json(raw_result),
        )
        elapsed_ms = int((perf_counter() - started) * 1000)
        tasks = normalize_q8_external_execution_tasks(
            raw_result,
            q2_functional_plugins=q2_functional_plugins,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q4_external_capabilities=q4_external_capabilities,
            q7_redlines=q7_redlines,
        )
        inference_payload = normalize_q8_inference_payload(
            raw_result,
            q2_functional_plugins=q2_functional_plugins,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q4_external_capabilities=q4_external_capabilities,
            q7_redlines=q7_redlines,
            request_scope="external",
        )
        if not tasks:
            task_queue = inference_payload.get("task_queue") if isinstance(inference_payload, dict) else {}
            tasks = list(task_queue.get("next_self_tasks") or []) if isinstance(task_queue, dict) else []
        finish_module_run(module_run)
        persist_question_module_output(
            context,
            question_id="q8",
            module_id="q8_external_task_generation",
            payload={
                "q8_external_llm_input": llm_input,
                "q8_external_llm_output": raw_result,
            },
            status=str(module_run.get("status") or "completed"),
            output_kind="inference",
        )
        token_usage = json_safe_payload(getattr(provider, "last_token_usage", None))
        token_usage = token_usage if isinstance(token_usage, dict) else {}
        trace_payload = {
            "request_id": request_id,
            "decision_id": scoped_decision_id,
            "provider_name": safe_provider_plugin_id(provider) or str(context.get("model_provider") or "").strip(),
            "model": _model_name(provider, context) or model_name,
            "system_prompt": request_payload["system_prompt"],
            "prompt": request_payload["prompt"],
            "source_module": caller_context.source_module,
            "invocation_phase": "nine_question_q8_external_decision",
            "question_driver_refs": caller_context.question_driver_refs,
            "context_data": request_payload["context"],
            "raw_response": raw_result,
            "token_usage": {
                "input_tokens": int(token_usage.get("input_tokens") or 0),
                "output_tokens": int(token_usage.get("output_tokens") or 0),
                "total_tokens": int(token_usage.get("total_tokens") or 0),
            },
            "elapsed_ms": elapsed_ms,
        }
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            source="plugins.nine_questions.q8_what_should_i_do_now.external_tasks",
            payload={
                "q8_external_llm_output": raw_result,
            },
        )
        _log(f"END external Q8 task generation {elapsed_ms / 1000:.3f}s tasks={len(tasks)}")
        return {
            "scope": "external",
            "raw_result": raw_result,
            "tasks": tasks,
            "inference_payload": inference_payload,
            "reasoning": reasoning,
            "trace_payload": trace_payload,
            "llm_input": llm_input,
            "llm_output": raw_result,
            "module_run": module_run,
            "task_plan": {
                "generated": tasks,
                "planner": "q8_external_task_generation",
            },
            "q2_functional_plugins": q2_functional_plugins,
            "q2_cognitive_plugins": q2_cognitive_plugins,
            "q4_external_capabilities": q4_external_capabilities,
            "q7_redlines": q7_redlines,
        }
    except Exception as exc:
        fail_module_run(
            module_run,
            status="failed",
            error_code="q8_external_task_generation_failed",
            error_message=str(exc),
        )
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            source="plugins.nine_questions.q8_what_should_i_do_now.external_tasks",
            payload={
                "request_id": request_id,
                "decision_id": scoped_decision_id,
                "question_ref": "我现在应该做什么",
                "caller_context": caller_context.model_dump(mode="json"),
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q8 EXTERNAL LLM ERROR] trace_id=%s error=%s", scoped_trace_id, exc)
        raise
