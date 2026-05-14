from __future__ import annotations

import json
import logging
from copy import deepcopy
from time import perf_counter
from typing import Any

from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.llm_request import (
    build_q8_external_staged_llm_request,
)
from plugins.nine_questions.q8_what_should_i_do_now.external_tasks.system_prompt import (
    build_q8_external_system_prompt,
)
from plugins.nine_questions.q8_what_should_i_do_now.llm_output_table import (
    save_q8_objective_llm_io_to_table,
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
from zentex.common.observable_logging import observable_event

logger = logging.getLogger(__name__)


def _log(event: str, **fields: Any) -> None:
    observable_event(
        logger,
        event,
        component="nine_questions.q8.external_tasks",
        question_id="q8",
        scope="external",
        **fields,
    )


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


def _q8_objective_number(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return _text(item.get("objective_number"))


def _q8_external_objective_slices(question_snapshot: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    q7 = _dict(question_snapshot.get("q7"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in _list(q7.get("external_creative_possibilities")):
        objective_number = _q8_objective_number(item)
        if objective_number:
            grouped.setdefault(objective_number, []).append(item)
    slices: list[tuple[str, dict[str, Any]]] = []
    for objective_number, possibilities in grouped.items():
        snapshot = deepcopy(question_snapshot)
        q7_slice = dict(_dict(snapshot.get("q7")))
        q7_slice["active_objective_number"] = objective_number
        q7_slice["external_creative_possibilities"] = possibilities
        snapshot["q7"] = q7_slice
        slices.append((objective_number, snapshot))
    return slices


def _merge_q8_inference_payloads(results: list[dict[str, Any]]) -> dict[str, Any]:
    objective: dict[str, Any] = {}
    queue = {"next_self_tasks": [], "blocked_self_tasks": [], "proactive_actions": []}
    for result in results:
        payload = _dict(result.get("inference_payload"))
        item_objective = _dict(payload.get("objective_profile"))
        if not objective:
            objective = {
                "current_mission": _text(item_objective.get("current_mission")),
                "mission_rationale": _text(item_objective.get("mission_rationale")),
                "primary_objectives": [],
                "secondary_objectives": [],
                "completion_conditions": [],
                "pause_conditions": [],
                "escalation_conditions": [],
                "current_phase_tasks": [],
                "priority_order": [],
            }
        for key in (
            "primary_objectives",
            "secondary_objectives",
            "completion_conditions",
            "pause_conditions",
            "escalation_conditions",
            "current_phase_tasks",
            "priority_order",
        ):
            objective[key] = merge_string_lists(
                list(objective.get(key) or []),
                [str(item) for item in _list(item_objective.get(key))],
            )
        if not objective.get("current_mission"):
            objective["current_mission"] = _text(item_objective.get("current_mission"))
        if not objective.get("mission_rationale"):
            objective["mission_rationale"] = _text(item_objective.get("mission_rationale"))
        item_queue = _dict(payload.get("task_queue"))
        for key in queue:
            queue[key].extend(_list(item_queue.get(key)))
    return {"objective_profile": objective, "task_queue": queue}


def _aggregate_q8_external_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    inference_payload = _merge_q8_inference_payloads(results)
    tasks: list[dict[str, Any]] = []
    trace_invocations: list[dict[str, Any]] = []
    objective_requests: list[dict[str, Any]] = []
    for result in results:
        tasks.extend(_list(result.get("tasks")))
        trace_payload = _dict(result.get("trace_payload"))
        if trace_payload:
            trace_invocations.append(trace_payload)
        objective_requests.append(
            {
                "objective_number": _text(result.get("objective_number")),
                "llm_input": _dict(result.get("llm_input")),
            }
        )
    return {
        "scope": "external",
        "raw_result": {
            "type": "Q8ExternalObjectiveProfileBatch",
            "objective_results": [
                {
                    "objective_number": _text(result.get("objective_number")),
                    "llm_output": _dict(result.get("llm_output")),
                }
                for result in results
            ],
        },
        "tasks": tasks,
        "inference_payload": inference_payload,
        "reasoning": {
            "decomposition_mode": "single_q7_objective_per_llm_call",
            "objective_count": len(results),
            "objectives": [_text(result.get("objective_number")) for result in results],
        },
        "trace_payload": {
            "invocation_phase": "nine_question_q8_external_decision_batch",
            "invocations": trace_invocations,
        },
        "llm_input": {
            "type": "Q8ExternalObjectiveRequestBatch",
            "objective_requests": objective_requests,
        },
        "llm_output": {
            "type": "Q8ExternalObjectiveProfileBatch",
            "objective_results": [
                {
                    "objective_number": _text(result.get("objective_number")),
                    "llm_output": _dict(result.get("llm_output")),
                }
                for result in results
            ],
        },
        "task_plan": {
            "generated": tasks,
            "planner": "q8_external_task_generation",
        },
    }


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


def _redline_payload(question_snapshot: dict[str, Any]) -> dict[str, Any]:
    q7 = _dict(question_snapshot.get("q7"))
    return {
        "q7_external_public_output": q7,
        "upstream_q6_public_output": _dict(q7.get("upstream_q6_public_output")),
        "external_creative_possibilities": _list(q7.get("external_creative_possibilities")),
        "ready_for_q4_objective_candidates": _list(q7.get("ready_for_q4_objective_candidates")),
        "needs_registration_possibilities": _list(q7.get("needs_registration_possibilities")),
        "possibility_statuses": _list(q7.get("possibility_statuses")),
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
    q7 = _dict(question_snapshot.get("q7"))

    for task in _list(priority_baseline.get("immediate_tasks")):
        candidates.append(
            _candidate(
                task,
                source_question="q8_priority_baseline",
                reason="Derived from the deterministic Q8 priority baseline.",
            )
        )
    for possibility in _list(q7.get("external_creative_possibilities")):
        if not isinstance(possibility, dict):
            continue
        title = _text(possibility.get("possibility_description"))
        if not title:
            continue
        candidates.append(
            _candidate(
                title,
                source_question="q7_external_output",
                reason=_text(possibility.get("divergent_rationale")) or "Derived from Q7 external creative possibility output.",
                required_capability=_text(possibility.get("possibility_type")),
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
    q7 = _dict(question_snapshot.get("q7"))
    forbidden = [
        str(item).lower()
        for item in (
            _list(q7.get("current_red_line_hits"))
            + _list(q7.get("non_bypassable_constraints"))
            + _list(q7.get("possibility_statuses"))
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
    if not context.get("q8_external_objective_slice_active"):
        objective_slices = _q8_external_objective_slices(question_snapshot)
        if objective_slices:
            _log(
                "q8_objective_batch_start",
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                objective_count=len(objective_slices),
                objective_numbers=[objective_number for objective_number, _ in objective_slices],
            )
            objective_results: list[dict[str, Any]] = []
            for objective_number, sliced_snapshot in objective_slices:
                _log(
                    "q8_objective_slice_start",
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=f"{trace_id}:external:{objective_number}",
                    objective_number=objective_number,
                )
                slice_context = {**context, "q8_external_objective_slice_active": True}
                result = run_q8_external_task_generation(
                    context=slice_context,
                    provider=provider,
                    transcript_store=transcript_store,
                    module_runs=module_runs,
                    question_snapshot=sliced_snapshot,
                    priority_baseline=priority_baseline,
                    normalized_task_state=normalized_task_state,
                    request_timeout_seconds=request_timeout_seconds,
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=f"{trace_id}:external:{objective_number}",
                    decision_id=decision_id,
                    request_id=request_id,
                )
                result["objective_number"] = objective_number
                save_q8_objective_llm_io_to_table(
                    db_path=context.get("nine_question_state_db_path"),
                    session_id=session_id,
                    lane="external",
                    objective_number=objective_number,
                    llm_input=_dict(result.get("llm_input")),
                    output_payload=_dict(result.get("llm_output")),
                    task_profile=result,
                )
                objective_results.append(result)
                _log(
                    "q8_objective_slice_completed",
                    session_id=session_id,
                    turn_id=turn_id,
                    trace_id=f"{trace_id}:external:{objective_number}",
                    objective_number=objective_number,
                    task_count=len(result.get("tasks") or []),
                )
            aggregate = _aggregate_q8_external_results(objective_results)
            persist_question_module_output(
                context,
                question_id="q8",
                module_id="q8_external_task_generation",
                payload={
                    "q8_external_llm_input": aggregate["llm_input"],
                    "q8_external_llm_output": aggregate["llm_output"],
                },
                status="completed",
                output_kind="inference",
            )
            _log(
                "q8_objective_batch_completed",
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                objective_count=len(objective_results),
                task_count=len(aggregate.get("tasks") or []),
            )
            return aggregate

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
        _log("q8_llm_request_build_start", session_id=session_id, turn_id=turn_id, trace_id=scoped_trace_id)
        q2_functional_plugins = _q2_functional_plugins(question_snapshot)
        q2_cognitive_plugins = _q2_cognitive_plugins(question_snapshot)
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
        }
        _log(
            "q8_llm_request_build_completed",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            candidate_count=len(candidate_tasks),
            allowed_count=len(allowed_tasks),
            blocked_count=len(blocked_tasks),
            cognitive_plugin_count=len(q2_cognitive_plugins),
            functional_plugin_count=len(q2_functional_plugins),
        )

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
        observable_event(
            logger,
            "q8_llm_input",
            component="nine_questions.q8.external_tasks",
            question_id="q8",
            scope="external",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            decision_id=scoped_decision_id,
            provider=safe_provider_plugin_id(provider),
            model=model_name or "unknown",
            llm_input=llm_input,
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
        observable_event(
            logger,
            "q8_llm_output",
            component="nine_questions.q8.external_tasks",
            question_id="q8",
            scope="external",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            decision_id=scoped_decision_id,
            provider=safe_provider_plugin_id(provider),
            model=_model_name(provider, context) or model_name or "unknown",
            llm_output=raw_result,
        )
        elapsed_ms = int((perf_counter() - started) * 1000)
        tasks = normalize_q8_external_execution_tasks(
            raw_result,
            q2_functional_plugins=q2_functional_plugins,
            q2_cognitive_plugins=q2_cognitive_plugins,
            q7_redlines=q7_redlines,
        )
        inference_payload = normalize_q8_inference_payload(
            raw_result,
            q2_functional_plugins=q2_functional_plugins,
            q2_cognitive_plugins=q2_cognitive_plugins,
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
        _log(
            "q8_task_generation_completed",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            decision_id=scoped_decision_id,
            elapsed_ms=elapsed_ms,
            task_count=len(tasks),
            token_usage=token_usage,
        )
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
        _log(
            "q8_task_generation_failed",
            session_id=session_id,
            turn_id=turn_id,
            trace_id=scoped_trace_id,
            decision_id=scoped_decision_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        raise
