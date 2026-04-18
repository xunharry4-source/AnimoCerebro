import logging
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.shared.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q8
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q8_what_should_i_do_now.models import (
    Q8InferenceResult,
)
from plugins.nine_questions.q8_what_should_i_do_now.llm_prompt import build_q8_llm_request

logger = logging.getLogger(__name__)


from zentex.common.nine_questions_shared import (
    build_caller_context,
    build_model_context,
    json_safe_payload,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_nine_questions_snapshot,
    render_plugin_catalog,
    render_task_state,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)
from zentex.plugins.service import (
    execute_enabled_cognitive_plugin_functionals,
)


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _normalize_snapshot_dict(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if str(key).strip()}


def _normalize_task_state(raw: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, list[dict[str, Any]]] = {}
    for status_key, value in raw.items():
        entries: list[dict[str, Any]] = []
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    entries.append(
                        {
                            "id": str(item.get("id") or f"{status_key}-{index}"),
                            "title": _normalize_text(item.get("title") or item.get("task") or item.get("id") or f"{status_key}-{index}"),
                            "status": _normalize_text(item.get("status") or status_key),
                            "priority": item.get("priority") if isinstance(item.get("priority"), int) else None,
                            "reason": _normalize_text(item.get("reason") or item.get("blocker_reason")),
                        }
                    )
                else:
                    text = _normalize_text(item)
                    if text:
                        entries.append(
                            {
                                "id": f"{status_key}-{index}",
                                "title": text,
                                "status": _normalize_text(status_key),
                                "priority": None,
                                "reason": "",
                            }
                        )
        if entries:
            normalized[str(status_key)] = entries
    return normalized


def _normalize_functional_objectives(raw_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        plugin_id = _normalize_text(item.get("plugin_id"))
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        normalized.append(
            {
                "plugin_id": plugin_id,
                "current_mission": _normalize_text(result.get("current_mission")),
                "primary_objectives": _coerce_string_list(result.get("primary_objectives")),
                "secondary_objectives": _coerce_string_list(result.get("secondary_objectives")),
                "current_phase_tasks": _coerce_string_list(result.get("current_phase_tasks")),
                "priority_order": _coerce_string_list(result.get("priority_order")),
                "completion_conditions": _coerce_string_list(result.get("completion_conditions")),
                "pause_conditions": _coerce_string_list(result.get("pause_conditions")),
                "escalation_conditions": _coerce_string_list(result.get("escalation_conditions")),
                "next_self_tasks": result.get("next_self_tasks") if isinstance(result.get("next_self_tasks"), list) else [],
                "blocked_self_tasks": result.get("blocked_self_tasks") if isinstance(result.get("blocked_self_tasks"), list) else [],
                "proactive_actions": result.get("proactive_actions") if isinstance(result.get("proactive_actions"), list) else [],
            }
        )
    return normalized


def _derive_priority_baseline(
    snapshot: dict[str, Any],
    question_snapshot: dict[str, Any],
    task_state: dict[str, list[dict[str, Any]]],
    functional_objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    q4 = question_snapshot.get("q4") if isinstance(question_snapshot.get("q4"), dict) else {}
    q5 = question_snapshot.get("q5") if isinstance(question_snapshot.get("q5"), dict) else {}
    q6 = question_snapshot.get("q6") if isinstance(question_snapshot.get("q6"), dict) else {}
    q7 = question_snapshot.get("q7") if isinstance(question_snapshot.get("q7"), dict) else {}
    q3 = question_snapshot.get("q3") if isinstance(question_snapshot.get("q3"), dict) else {}

    immediate_tasks: list[str] = []
    blocked_tasks: list[str] = []
    proactive_actions: list[str] = []
    escalation_conditions: list[str] = []

    actionable_space = _coerce_string_list(q4.get("actionable_space"))
    fallback_plans = _coerce_string_list(q7.get("fallback_plans"))
    resource_gaps = _coerce_string_list(q3.get("missing_critical_assets"))
    absolute_red_lines = _coerce_string_list(q6.get("absolute_red_lines"))
    forbidden_actions = _coerce_string_list(q5.get("explicitly_forbidden_actions"))

    if actionable_space:
        immediate_tasks.extend([f"execute within validated action space: {item}" for item in actionable_space[:3]])
    else:
        immediate_tasks.append("rebuild actionable space evidence before execution")

    if fallback_plans:
        proactive_actions.extend([f"prepare fallback branch: {item}" for item in fallback_plans[:3]])
    if resource_gaps:
        blocked_tasks.extend([f"resolve resource gap: {item}" for item in resource_gaps[:3]])
    escalation_conditions.extend([f"red-line conflict detected: {item}" for item in absolute_red_lines[:3]])
    escalation_conditions.extend([f"forbidden action requested: {item}" for item in forbidden_actions[:3]])

    for status_key, entries in task_state.items():
        for entry in entries[:5]:
            title = _normalize_text(entry.get("title"))
            reason = _normalize_text(entry.get("reason"))
            if status_key in {"blocked", "waiting", "paused"}:
                blocked_tasks.append(f"{title}: {reason}" if reason else title)
            else:
                immediate_tasks.append(title)

    for item in functional_objectives:
        immediate_tasks.extend(_coerce_string_list(item.get("current_phase_tasks"))[:2])
        proactive_actions.extend(_coerce_string_list(item.get("priority_order"))[:2])
        escalation_conditions.extend(_coerce_string_list(item.get("escalation_conditions"))[:2])

    return {
        "immediate_tasks": list(dict.fromkeys(item for item in immediate_tasks if _normalize_text(item))),
        "blocked_tasks": list(dict.fromkeys(item for item in blocked_tasks if _normalize_text(item))),
        "proactive_actions": list(dict.fromkeys(item for item in proactive_actions if _normalize_text(item))),
        "escalation_conditions": list(dict.fromkeys(item for item in escalation_conditions if _normalize_text(item))),
    }


def _merge_string_lists(primary: list[str], baseline: list[str]) -> list[str]:
    return list(dict.fromkeys(_coerce_string_list(primary) + _coerce_string_list(baseline)))


def _merge_task_rows(primary: list[dict[str, Any]], baseline_titles: list[str], status: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in primary:
        if not isinstance(item, dict):
            continue
        title = _normalize_text(item.get("title") or item.get("task") or item.get("task_id") or item.get("id"))
        if not title or title in seen:
            continue
        seen.add(title)
        merged.append(dict(item))
    for index, title in enumerate(_coerce_string_list(baseline_titles)):
        if title in seen:
            continue
        seen.add(title)
        merged.append({"task_id": f"{status}-{index}", "title": title, "status": status})
    return merged


class WhatShouldIDoNowPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    """
    [LLM MANDATORY] Q8 Phase Plugin.
    Synopsizes Q1-Q7 to generate the current focus and task queue.
    The core decision hub for the Zentex G31A Autonomous Controller.
    """
    plugin_id: str = NINE_QUESTION_Q8
    display_name: str = "Q8: What should I do now? (Decision & Tasking)"
    behavior_key: str = "q8_final_decision"
    version: str = "1.0.0"
    is_concurrency_safe: bool = True
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    rollback_conditions: List[str] = ["unhandled_llm_failure"]
    revocation_reasons: List[str] = []
    tool_type: str = "nine_question"
    purpose: str = "Synthesize current primary objective and task queue under Q1-Q7 constraints."
    input_schema: Dict[str, Any] = {"type": "object"}
    output_schema: Dict[str, Any] = {"type": "object"}
    required_context: List[str] = ["nine_questions", "persistent_task_state", "plugin_service", "transcript_store", "llm_service"]
    trigger_conditions: List[str] = ["inspection", "always"]
    do_not_use_when: List[str] = ["missing_llm_service"]
    read_only: bool = True
    side_effect_free: bool = True
    is_default_version: bool = True
    is_official_release: bool = True

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize current primary objective and tasks.
        """
        provider = require_model_provider(context)
        snapshot = context.get("context_snapshot", {}) or {}
        transcript_store = require_transcript_store(context)
        question_snapshot = _normalize_snapshot_dict(
            snapshot.get("q1_q7_snapshot") or context.get("q1_q7_snapshot") or {}
        )
        normalized_task_state = _normalize_task_state(
            context.get("persistent_task_state") or snapshot.get("persistent_task_state")
        )
        
        plugin_service = context.get("plugin_service")
        trace_id = str(context.get("trace_id") or f"q8-decision:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")

        functional_objectives: list[dict[str, Any]] = []
        obj_oracles: list[str] = []
        if plugin_service is not None:
            functional_objectives = execute_enabled_cognitive_plugin_functionals(
                plugin_service,
                self.plugin_id,
                default_parameters={
                    "task_queue": list(context.get("persistent_task_state", []) or []),
                    "context": dict(context),
                },
                trace_id=trace_id,
                originator_id=session_id,
                caller_plugin_id=self.plugin_id,
            )
            obj_oracles = [
                str(item.get("plugin_id") or "")
                for item in functional_objectives
                if item.get("status") == "done"
            ]
        normalized_functional_objectives = _normalize_functional_objectives(
            [
                {
                    "plugin_id": item.get("plugin_id"),
                    "result": item.get("result"),
                }
                for item in functional_objectives
                if item.get("status") == "done"
            ]
        )
        priority_baseline = _derive_priority_baseline(
            snapshot,
            question_snapshot,
            normalized_task_state,
            normalized_functional_objectives,
        )

        # 3. Build synthesis prompt
        system_prompt = (
            "你现在是 Zentex 外部大脑的主目标生成与任务排序中枢。请严格审查传入的 Q1-Q7 约束条件。\n"
            "你的任务是：在绝对不违背 Q5（权限）和 Q6（红线）的前提下，基于 Q3/Q4 的真实能力，"
            "推断现在最应该推进的主目标是什么？当前阶段的具体任务是什么？"
        )
        objective_catalog = render_plugin_catalog(obj_oracles, heading="可用目标策略插件")
        nine_questions_summary = render_nine_questions_snapshot(question_snapshot or snapshot.get("nine_questions") or context.get("nine_questions"))
        task_state_summary = render_task_state(normalized_task_state)

        llm_request = build_q8_llm_request(
            system_prompt=system_prompt,
            nine_questions_summary=nine_questions_summary,
            task_state_summary=task_state_summary,
            objective_catalog=objective_catalog,
            priority_baseline=priority_baseline,
            q1_q7_snapshot=question_snapshot,
            nine_questions=snapshot.get("nine_questions") or context.get("nine_questions") or {},
            persistent_task_state=normalized_task_state,
            active_objectives=obj_oracles,
            functional_objectives=normalized_functional_objectives,
        )
        user_prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        # 4. Invoke LLM with strict traceability
        caller_context = build_caller_context(
            invocation_phase="nine_question_q8_decision",
            source_module="q8_what_should_i_do_now_plugin",
            question_ref="我现在应该做什么",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q8_what_should_i_do_now",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": "我现在应该做什么",
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        try:
            started = perf_counter()
            result_raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{user_prompt}",
                context=model_context,
                caller_context=caller_context
            )
            elapsed_ms = int((perf_counter() - started) * 1000)

            # 5. Validate & Return
            inference = Q8InferenceResult.model_validate(result_raw)
            inferred_objective = inference.objective_profile
            inferred_queue = inference.task_queue
            objective = inferred_objective.model_copy(
                update={
                    "current_phase_tasks": _merge_string_lists(
                        inferred_objective.current_phase_tasks,
                        priority_baseline.get("immediate_tasks", []),
                    ),
                    "priority_order": _merge_string_lists(
                        inferred_objective.priority_order,
                        priority_baseline.get("immediate_tasks", []),
                    ),
                    "escalation_conditions": _merge_string_lists(
                        inferred_objective.escalation_conditions,
                        priority_baseline.get("escalation_conditions", []),
                    ),
                }
            )
            queue = inferred_queue.model_copy(
                update={
                    "next_self_tasks": _merge_task_rows(
                        inferred_queue.next_self_tasks,
                        priority_baseline.get("immediate_tasks", []),
                        "next",
                    ),
                    "blocked_self_tasks": _merge_task_rows(
                        inferred_queue.blocked_self_tasks,
                        priority_baseline.get("blocked_tasks", []),
                        "blocked",
                    ),
                    "proactive_actions": _merge_task_rows(
                        inferred_queue.proactive_actions,
                        priority_baseline.get("proactive_actions", []),
                        "proactive",
                    ),
                }
            )

            record_model_completed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q8_what_should_i_do_now",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我现在应该做什么",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "result": inference.model_dump(mode="json"),
                    "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                    "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                    "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                    "elapsed_ms": elapsed_ms,
                },
            )

            # Return as a flattened dictionary for the state machine
            return {
                "objective": objective.model_dump(mode="json"),
                "task_queue": queue.model_dump(mode="json"),
                "q1_q7_snapshot": question_snapshot,
                "persistent_task_state": normalized_task_state,
                "q8_priority_baseline": priority_baseline,
                "q8_functional_objectives": normalized_functional_objectives,
            }

        except Exception as exc:
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q8_what_should_i_do_now",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": "我现在应该做什么",
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            logger.error(f"Q8 LLM Failure: {exc}")
            raise RuntimeError(f"[LLM MANDATORY] Q8 synthesis failed: {exc}") from exc

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        result = self.execute(dict(context))
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Synthesized objective and task queue (Q8)",
            proposals=[
                {
                    "kind": "nine_question_q8_decision",
                    "result": result,
                }
            ],
            context_updates={
                "q8_objective_and_queue": result,
                "q8_objective_profile": result.get("objective"),
                "q8_task_queue": result.get("task_queue"),
                "q8_q1_q7_snapshot": result.get("q1_q7_snapshot") or {},
                "q8_persistent_task_state": result.get("persistent_task_state") or {},
                "q8_priority_baseline": result.get("q8_priority_baseline") or {},
                "q8_functional_objectives": result.get("q8_functional_objectives") or [],
            },
            confidence=0.8,
        )


def build_q8_what_should_i_do_now_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q8,
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> WhatShouldIDoNowPlugin:
    return WhatShouldIDoNowPlugin(
        plugin_id=plugin_id,
        feature_code="nine_questions.q8",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )
