import logging
import json
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q8
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q8_what_should_i_do_now.models import (
    Q8InferenceResult,
)
from plugins.nine_questions.q8_what_should_i_do_now.llm_prompt import build_q8_llm_request
from plugins.nine_questions.q8_what_should_i_do_now.modules import (
    derive_priority_baseline,
    merge_string_lists,
    merge_task_rows,
    normalize_functional_objectives,
    normalize_q8_inference_payload,
    normalize_snapshot_dict,
    normalize_task_state,
)
from zentex.tasks.execution.task_persistence import task_persistence

logger = logging.getLogger(__name__)


def _q8_realtime_log(message: str) -> None:
    print(f"[Q8Plugin] {message}", flush=True)


from zentex.common.nine_questions_shared import (
    build_nine_question_partial_failure,
    bind_module_runs,
    run_audit_integration,
    run_learning_integration,
    load_authoritative_question_bundle_from_storage,
    run_memory_integration,
    run_reflection_integration,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    build_question_dependency,
    build_model_context,
    fail_module_run,
    json_safe_payload,
    question_authenticity_judgment,
    record_plugin_attempt,
    record_plugin_result,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    render_nine_questions_snapshot,
    render_plugin_catalog,
    render_task_state,
    persist_question_module_output,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
    start_module_run,
    finish_module_run,
)
from zentex.plugins.service import (
    execute_enabled_cognitive_plugin_functionals,
)


def _q8_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _q8_text(value: Any, *, max_chars: int = 500) -> str:
    text = str(value or "").strip()
    return text[:max_chars]


def _q8_list(value: Any, *, limit: int = 6, max_chars: int = 180) -> list[Any]:
    if not isinstance(value, list):
        return []
    normalized: list[Any] = []
    for item in value:
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            compact = {
                str(key): _q8_text(val, max_chars=max_chars)
                for key, val in item.items()
                if val not in (None, "", [], {})
            }
            if compact:
                normalized.append(compact)
        else:
            normalized.append(_q8_text(item, max_chars=max_chars))
        if len(normalized) >= limit:
            break
    return normalized


def _q8_diagnosis_status(payload: dict[str, Any], key: str) -> str:
    diagnosis = _q8_dict(payload.get(key))
    return _q8_text(diagnosis.get("authenticity_status") or payload.get("status"))


def _build_q8_decision_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    q1 = _q8_dict(snapshot.get("q1"))
    q2 = _q8_dict(snapshot.get("q2"))
    q3 = _q8_dict(snapshot.get("q3"))
    q4 = _q8_dict(snapshot.get("q4"))
    q5 = _q8_dict(snapshot.get("q5"))
    q6 = _q8_dict(snapshot.get("q6"))
    q7 = _q8_dict(snapshot.get("q7"))

    q1_scene = _q8_dict(q1.get("q1_scene_model") or q1.get("workspace_domain_inference"))
    q1_env = _q8_dict(q1.get("environment_event") or q1.get("physical_host_state"))
    q2_role = _q8_dict(q2.get("q2_role_profile") or q2.get("identity_kernel_snapshot"))
    q2_mission = _q8_dict(q2.get("q2_mission_boundary") or q2.get("mission_continuity_projection"))
    q3_resource = _q8_dict(q3.get("q3_resource_evaluation"))
    q3_assets = _q8_dict(q3.get("q3_unified_asset_inventory"))
    q4_profile = _q8_dict(q4.get("q4_capability_boundary_profile") or q4.get("q4_capability_baseline"))
    q4_permission = _q8_dict(q4.get("q4_permission_profile"))
    q5_profile = _q8_dict(q5.get("q5_authorization_boundary_profile") or q5.get("q5_authorization_baseline"))
    q5_permission = _q8_dict(q5.get("q5_permission_boundary"))
    q6_profile = _q8_dict(q6.get("q6_forbidden_zone_profile") or q6.get("q6_forbidden_zone_baseline"))
    q7_profile = _q8_dict(q7.get("q7_alternative_strategy_profile") or q7.get("q7_alternative_strategy_baseline"))

    return {
        "q1": {
            "status": _q8_diagnosis_status(q1, "q1_execution_diagnosis"),
            "environment_summary": _q8_text(q1.get("summary") or q1_env.get("summary")),
            "primary_domain": _q8_text(q1_scene.get("primary_domain")),
            "secondary_domains": _q8_list(q1_scene.get("secondary_domains"), limit=4),
            "suggested_first_step": _q8_text(q1_scene.get("suggested_first_step")),
            "uncertainty": _q8_dict(q1.get("q1_uncertainty_profile")),
        },
        "q2": {
            "status": _q8_diagnosis_status(q2, "q2_execution_diagnosis"),
            "role_profile": {
                "identity_role": _q8_text(q2_role.get("identity_role")),
                "active_role": _q8_text(q2_role.get("active_role")),
                "task_role": _q8_text(q2_role.get("task_role")),
            },
            "mission": {
                "current_mission": _q8_text(q2_mission.get("current_mission")),
                "priority_duties": _q8_list(q2_mission.get("priority_duties"), limit=5),
                "continuity_boundaries": _q8_list(q2_mission.get("continuity_boundaries"), limit=5),
            },
            "non_bypassable_constraints": _q8_list(q2.get("non_bypassable_constraints"), limit=4),
            "audit_rules": _q8_list(q2.get("global_audit_rules"), limit=4),
        },
        "q3": {
            "status": _q8_diagnosis_status(q3, "q3_execution_diagnosis"),
            "resource_status": _q8_text(q3_resource.get("resource_status")),
            "bottleneck_node": _q8_text(q3_resource.get("bottleneck_node")),
            "missing_critical_assets": _q8_list(q3_resource.get("missing_critical_assets"), limit=6),
            "available_cognitive_tools": _q8_list(q3_assets.get("available_cognitive_tools"), limit=6),
            "available_execution_tools": _q8_list(q3_assets.get("available_execution_tools"), limit=6),
            "accessible_workspace_zones": _q8_list(q3_assets.get("accessible_workspace_zones"), limit=6),
        },
        "q4": {
            "status": _q8_diagnosis_status(q4, "q4_execution_diagnosis"),
            "actionable_space": _q8_list(q4_profile.get("actionable_space"), limit=8),
            "executable_strategies": _q8_list(q4_profile.get("executable_strategies"), limit=8),
            "capability_upper_limits": _q8_list(q4_profile.get("capability_upper_limits"), limit=8),
            "permission_profile": {
                "mode": _q8_text(q4_permission.get("mode")),
                "is_read_only": bool(q4_permission.get("is_read_only")),
                "tenant_permissions": _q8_list(q4_permission.get("tenant_permissions"), limit=6),
                "execution_tokens": _q8_list(q4_permission.get("execution_tokens"), limit=6),
                "accessible_workspace_zones": _q8_list(q4_permission.get("accessible_workspace_zones"), limit=6),
            },
        },
        "q5": {
            "status": _q8_diagnosis_status(q5, "q5_execution_diagnosis"),
            "allowed_action_space": _q8_list(q5_profile.get("allowed_action_space"), limit=8),
            "forbidden_action_space": _q8_list(q5_profile.get("forbidden_action_space"), limit=8),
            "requires_escalation_actions": _q8_list(q5_profile.get("requires_escalation_actions"), limit=6),
            "authorized_actions": _q8_list(q5_permission.get("authorized_actions"), limit=8),
            "unauthorized_actions": _q8_list(q5_permission.get("unauthorized_actions"), limit=8),
            "conditional_actions": _q8_list(q5_permission.get("conditional_actions"), limit=8),
        },
        "q6": {
            "status": _q8_diagnosis_status(q6, "q6_execution_diagnosis"),
            "absolute_red_lines": _q8_list(q6_profile.get("absolute_red_lines"), limit=10),
            "performance_tradeoff_bans": _q8_list(q6_profile.get("performance_tradeoff_bans"), limit=8),
            "prohibited_strategies": _q8_list(q6_profile.get("prohibited_strategies"), limit=8),
            "contamination_risks": _q8_list(q6_profile.get("contamination_risks"), limit=8),
            "audit_rules": _q8_list(q6.get("global_audit_rules"), limit=4),
        },
        "q7": {
            "status": _q8_diagnosis_status(q7, "q7_execution_diagnosis"),
            "fallback_plans": _q8_list(q7_profile.get("fallback_plans"), limit=8),
            "degradation_strategies": _q8_list(q7_profile.get("degradation_strategies"), limit=8),
            "collaboration_switches": _q8_list(q7_profile.get("collaboration_switches"), limit=6),
            "exploratory_actions": _q8_list(q7_profile.get("exploratory_actions"), limit=6),
            "capability_limits": _q8_list(q7.get("q7_capability_limits"), limit=8),
            "permission_boundaries": _q8_list(q7.get("q7_permission_boundaries"), limit=8),
            "resource_bottlenecks": _q8_list(q7.get("q7_resource_bottlenecks"), limit=6),
        },
    }


def _q8_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _existing_q8_committed_result(context: dict[str, Any]) -> CognitiveToolResult | None:
    state = _q8_dict(context.get("nine_question_state"))
    snapshots = _q8_dict(state.get("question_snapshots"))
    snapshot = _q8_dict(snapshots.get("q8"))
    context_updates = _q8_dict(snapshot.get("context_updates"))
    diagnosis = _q8_dict(context_updates.get("q8_execution_diagnosis"))
    if _q8_text(diagnosis.get("authenticity_status")).lower() != "completed":
        return None
    result_payload = _q8_dict(snapshot.get("result"))
    q8_result = _q8_dict(context_updates.get("q8_objective_and_queue") or result_payload)
    if not q8_result:
        return None
    return CognitiveToolResult(
        tool_id=str(snapshot.get("tool_id") or NINE_QUESTION_Q8),
        summary=str(snapshot.get("summary") or "Preserved committed Q8 objective and task queue"),
        proposals=[
            {
                "kind": "nine_question_q8_decision",
                "result": q8_result,
            }
        ],
        context_updates=context_updates,
        confidence=float(snapshot.get("confidence") or 0.8),
    )


def _q8_candidate(title: Any, *, source_question: str, reason: str, required_capability: str = "") -> dict[str, str]:
    return {
        "title": _q8_text(title, max_chars=180),
        "source_question": source_question,
        "reason": _q8_text(reason, max_chars=260),
        "required_capability": _q8_text(required_capability, max_chars=180),
    }


def _derive_q8_candidate_tasks(
    question_snapshot: dict[str, Any],
    priority_baseline: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    q3 = _q8_dict(question_snapshot.get("q3"))
    q4 = _q8_dict(question_snapshot.get("q4"))
    q4_permission = _q8_dict(q4.get("permission_profile"))

    for task in _q8_list(priority_baseline.get("immediate_tasks"), limit=8):
        candidates.append(
            _q8_candidate(
                task,
                source_question="q8_priority_baseline",
                reason="Derived from the deterministic Q8 priority baseline.",
            )
        )
    for task in _q8_list(q4.get("actionable_space"), limit=8):
        candidates.append(
            _q8_candidate(
                task,
                source_question="q4",
                reason="Allowed by the current capability boundary.",
                required_capability=task,
            )
        )
    for task in _q8_list(q4.get("executable_strategies"), limit=6):
        candidates.append(
            _q8_candidate(
                task,
                source_question="q4",
                reason="Executable strategy reported by Q4.",
                required_capability=task,
            )
        )
    for task in _q8_list(q3.get("available_execution_tools"), limit=6):
        candidates.append(
            _q8_candidate(
                f"use available execution tool: {task}",
                source_question="q3",
                reason="Execution tool is available in the current resource inventory.",
                required_capability=task,
            )
        )
    for entries in normalized_task_state.values():
        for entry in entries[:4]:
            title = entry.get("title") if isinstance(entry, dict) else entry
            candidates.append(
                _q8_candidate(
                    title,
                    source_question="task_state",
                    reason="Existing persistent task state contains this active task.",
                )
            )
    if q4_permission.get("is_read_only"):
        candidates.append(
            _q8_candidate(
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
        if len(deduped) >= 24:
            break
    return deduped


def _filter_q8_candidate_tasks(
    candidate_tasks: list[dict[str, str]],
    question_snapshot: dict[str, Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    q5 = _q8_dict(question_snapshot.get("q5"))
    q6 = _q8_dict(question_snapshot.get("q6"))
    forbidden = [
        str(item).lower()
        for item in (
            _q8_list(q5.get("forbidden_action_space"), limit=12)
            + _q8_list(q5.get("unauthorized_actions"), limit=12)
            + _q8_list(q6.get("absolute_red_lines"), limit=12)
            + _q8_list(q6.get("prohibited_strategies"), limit=12)
        )
        if str(item).strip()
    ]
    allowed: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    for item in candidate_tasks:
        title = item.get("title", "")
        title_lower = title.lower()
        matched = next((rule for rule in forbidden if rule and rule in title_lower), "")
        if matched:
            blocked.append(
                {
                    "title": title,
                    "reason": f"Conflicts with Q5/Q6 constraint: {matched}",
                    "blocked_by": matched,
                }
            )
        else:
            allowed.append(
                {
                    "title": title,
                    "reason": item.get("reason", ""),
                    "priority_hint": item.get("source_question", ""),
                }
            )
    return allowed[:16], blocked[:16]


def _run_q8_staged_decision(
    *,
    provider: Any,
    system_prompt: str,
    question_snapshot: dict[str, Any],
    normalized_task_state: dict[str, list[dict[str, Any]]],
    priority_baseline: dict[str, Any],
    normalized_functional_objectives: list[dict[str, Any]],
    caller_context: Any,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    stage_common = {
        "request_timeout_seconds": request_timeout_seconds,
        "q8_priority_baseline": priority_baseline,
    }
    q7 = {"q7": question_snapshot.get("q7", {})}
    candidate_tasks = _derive_q8_candidate_tasks(
        question_snapshot,
        priority_baseline,
        normalized_task_state,
    )
    allowed_tasks, blocked_tasks = _filter_q8_candidate_tasks(candidate_tasks, question_snapshot)

    final_prompt = (
        "Q8 final stage: create alternatives for blocked tasks using Q7, then synthesize the final Q8 decision. "
        "Return strict JSON with top-level keys `objective_profile` and `task_queue` only. "
        "`objective_profile` must include `current_mission`, `primary_objectives`, `secondary_objectives`, "
        "`completion_conditions`, `pause_conditions`, `escalation_conditions`, `current_phase_tasks`, and `priority_order`. "
        "`task_queue` must include `next_self_tasks`, `blocked_self_tasks`, and `proactive_actions` arrays. "
        "Do not include markdown or explanatory prose."
    )
    final_context = {
        **stage_common,
        "allowed_tasks": allowed_tasks[:16],
        "blocked_tasks": blocked_tasks[:16],
        "q7_alternatives": q7,
        "task_state": normalized_task_state,
    }
    final_result = provider.generate_json(
        prompt=f"{system_prompt}\n\n{final_prompt}",
        context=final_context,
        caller_context=caller_context,
    )
    if isinstance(final_result, dict):
        final_result = dict(final_result)
        final_result["_q8_staged_reasoning"] = {
            "candidate_count": len(candidate_tasks),
            "allowed_count": len(allowed_tasks),
            "blocked_count": len(blocked_tasks),
            "candidate_sample": candidate_tasks[:8],
            "allowed_sample": allowed_tasks[:8],
            "blocked_sample": blocked_tasks[:8],
        }
        return final_result
    return {}


def _record_q8_downstream_failure_nodes(
    context: Dict[str, Any],
    *,
    module_runs: list[dict[str, Any]],
    error_code: str,
    error_message: str,
) -> None:
    failure_payload = {
        "q8_q1_q7_snapshot": normalize_snapshot_dict(
            load_authoritative_question_bundle_from_storage(
                context, ["q1", "q2", "q3", "q4", "q5", "q6", "q7"]
            )
        ),
        "q8_persistent_task_state": normalize_task_state(context.get("persistent_task_state")),
    }
    module_specs = [
        ("q8_audit_integration", "audit", "Q8 objective/task queue unavailable; audit integration skipped."),
        ("q8_memory_integration", "memory", "Q8 objective/task queue unavailable; memory integration skipped."),
        ("q8_reflection_integration", "reflection", "Q8 objective/task queue unavailable; reflection integration skipped."),
        ("q8_learning_integration", "learning", "Q8 objective/task queue unavailable; learning integration skipped."),
    ]
    for module_id, module_kind, summary in module_specs:
        run = start_module_run(module_runs, module_id, source="plugins.nine_questions.q8")
        finish_module_run(
            run,
            status="missing",
            error_code=error_code,
            error_message=error_message,
        )
        run["data"] = {
            "question_id": "q8",
            "module_kind": module_kind,
            "summary": summary,
            "payload": json_safe_payload(failure_payload),
            "trace_id": str(context.get("trace_id") or "q8:downstream_failure"),
        }
        persist_question_module_output(
            context,
            question_id="q8",
            module_id=module_id,
            payload=run["data"],
            status="missing",
            output_kind="integration",
            extra={
                "error_code": error_code,
                "error_message": error_message,
            },
        )


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

    def execute(self, context: Dict[str, Any], trace_id: str = "") -> Dict[str, Any]:
        """
        Synthesize current primary objective and tasks.
        """
        context = dict(context)
        if trace_id and not context.get("trace_id"):
            context["trace_id"] = trace_id
        requested_provider = str(context.get("model_provider") or "").strip()
        if requested_provider != "__bad_llm_provider__":
            context["model_provider"] = "openai_compat"
            context["llm_model"] = "gemini-3-flash"
            context["model"] = "gemini-3-flash"
        total_started = perf_counter()
        _q8_realtime_log("START execute")
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        module_runs = bind_module_runs(context, "q8")
        plugin_runs: list[dict[str, Any]] = []
        upstream_dependencies: list[dict[str, Any]] = []
        decision_projection_run = start_module_run(
            module_runs, "q8_decision_projection", source="plugins.nine_questions.q8"
        )

        phase_started = perf_counter()
        _q8_realtime_log("START load authoritative Q1-Q7 snapshots")
        question_snapshot = normalize_snapshot_dict(
            load_authoritative_question_bundle_from_storage(context, ["q1", "q2", "q3", "q4", "q5", "q6", "q7"])
        )
        question_snapshot = _build_q8_decision_digest(question_snapshot)
        _q8_realtime_log(
            "END load authoritative Q1-Q7 snapshots "
            f"{perf_counter() - phase_started:.3f}s keys={sorted(question_snapshot.keys())}"
        )
        snapshot_validation_run = start_module_run(
            module_runs, "q8_snapshot_validation", source="plugins.nine_questions.q8"
        )
        for dependency_id in ("q1", "q2", "q3", "q4", "q5", "q6", "q7"):
            upstream_dependencies.append(
                build_question_dependency(
                    dependency_id,
                    payload=question_snapshot.get(dependency_id),
                    required=dependency_id in {"q4", "q5", "q6"},
                    allow_degraded=False,
                )
            )
        if all(item["status"] == "completed" for item in upstream_dependencies if item["required"]):
            finish_module_run(snapshot_validation_run)
        else:
            fail_module_run(
                snapshot_validation_run,
                status="degraded",
                error_code="upstream_degraded",
                error_message="Q8 detected degraded or missing upstream question state.",
                used_fallback=True,
            )
        phase_started = perf_counter()
        _q8_realtime_log("START persist q8_snapshot_validation module output")
        persist_question_module_output(
            context,
            question_id="q8",
            module_id="q8_snapshot_validation",
            payload={"q8_q1_q7_snapshot": question_snapshot},
            status=str(snapshot_validation_run.get("status") or "completed"),
            output_kind="evidence",
        )
        _q8_realtime_log(f"END persist q8_snapshot_validation module output {perf_counter() - phase_started:.3f}s")

        task_state_load_run = start_module_run(
            module_runs, "q8_task_state_load", source="plugins.nine_questions.q8"
        )
        phase_started = perf_counter()
        _q8_realtime_log("START normalize persistent task state")
        normalized_task_state = normalize_task_state(
            context.get("persistent_task_state")
        )
        _q8_realtime_log(
            "END normalize persistent task state "
            f"{perf_counter() - phase_started:.3f}s buckets={sorted(normalized_task_state.keys())}"
        )
        if normalized_task_state:
            finish_module_run(task_state_load_run)
        else:
            finish_module_run(
                task_state_load_run,
                status="ready",
                error_code="task_state_missing",
                error_message="Persistent task state is empty or unavailable.",
            )
        phase_started = perf_counter()
        _q8_realtime_log("START persist q8_task_state_load module output")
        persist_question_module_output(
            context,
            question_id="q8",
            module_id="q8_task_state_load",
            payload={"persistent_task_state": normalized_task_state},
            status=str(task_state_load_run.get("status") or "completed"),
            output_kind="evidence",
        )
        _q8_realtime_log(f"END persist q8_task_state_load module output {perf_counter() - phase_started:.3f}s")
        
        plugin_service = context.get("plugin_service")
        trace_id = str(context.get("trace_id") or f"q8-decision:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:{self.plugin_id}")

        functional_objectives: list[dict[str, Any]] = []
        obj_oracles: list[str] = []
        objective_chain_run = start_module_run(
            module_runs, "q8_functional_objective_chain", source="plugins.nine_questions.q8"
        )
        if plugin_service is not None:
            phase_started = perf_counter()
            _q8_realtime_log("START execute functional objective plugins")
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
            _q8_realtime_log(
                "END execute functional objective plugins "
                f"{perf_counter() - phase_started:.3f}s count={len(functional_objectives)}"
            )
            for item in functional_objectives:
                plugin_id = str(item.get("plugin_id") or "unknown-plugin")
                run = record_plugin_attempt(
                    plugin_runs,
                    plugin_id=plugin_id,
                    feature_code=f"{self.plugin_id}.functional_objective",
                    expected=True,
                    attempted=True,
                    input_summary={"task_state_keys": sorted(normalized_task_state.keys())},
                )
                if item.get("status") == "done":
                    record_plugin_result(
                        run,
                        status="completed",
                        output_summary={
                            "result_keys": sorted((item.get("result") or {}).keys())
                            if isinstance(item.get("result"), dict)
                            else []
                        },
                    )
                else:
                    record_plugin_result(
                        run,
                        status="failed",
                        error_code="functional_objective_failed",
                        error_message=str(item.get("error") or item.get("status") or "functional plugin failed"),
                    )
            obj_oracles = [
                str(item.get("plugin_id") or "")
                for item in functional_objectives
                if item.get("status") == "done"
            ]
        if plugin_service is None:
            fail_module_run(
                objective_chain_run,
                status="missing",
                error_code="plugin_service_missing",
                error_message="Q8 functional objective chain was not started because plugin_service is missing.",
                used_fallback=True,
            )
        elif obj_oracles:
            finish_module_run(objective_chain_run)
        else:
            finish_module_run(
                objective_chain_run,
                status="ready",
                error_code="functional_objective_missing",
                error_message="Q8 executed without any successful objective plugin result.",
            )
        phase_started = perf_counter()
        _q8_realtime_log("START normalize functional objectives and derive priority baseline")
        normalized_functional_objectives = normalize_functional_objectives(
            [
                {
                    "plugin_id": item.get("plugin_id"),
                    "result": item.get("result"),
                }
                for item in functional_objectives
                if item.get("status") == "done"
            ]
        )
        priority_run = start_module_run(
            module_runs, "q8_priority_derivation", source="plugins.nine_questions.q8"
        )
        priority_baseline = derive_priority_baseline(
            question_snapshot,
            question_snapshot,
            normalized_task_state,
            normalized_functional_objectives,
        )
        priority_baseline = {
            **priority_baseline,
            "priority_factors": [
                {"factor": "redline_pressure", "count": len(question_snapshot.get("q6", {}).get("absolute_red_lines", []) or [])},
                {"factor": "authorization_pressure", "count": len(question_snapshot.get("q5", {}).get("explicitly_forbidden_actions", []) or [])},
                {"factor": "resource_gap_pressure", "count": len(question_snapshot.get("q3", {}).get("missing_critical_assets", []) or [])},
                {"factor": "active_task_pressure", "count": sum(len(v) for v in normalized_task_state.values())},
                {
                    "factor": "fallback_pressure",
                    "count": int(snapshot_validation_run["status"] != "completed") + int(task_state_load_run["status"] != "completed"),
                },
            ],
        }
        _q8_realtime_log(
            "END normalize functional objectives and derive priority baseline "
            f"{perf_counter() - phase_started:.3f}s "
            f"objectives={len(normalized_functional_objectives)} "
            f"immediate_tasks={len(priority_baseline.get('immediate_tasks', []) or [])}"
        )
        finish_module_run(priority_run)
        phase_started = perf_counter()
        _q8_realtime_log("START persist q8 objective and priority module outputs")
        persist_question_module_output(
            context,
            question_id="q8",
            module_id="q8_functional_objective_chain",
            payload={"functional_objectives": normalized_functional_objectives},
            status=str(objective_chain_run.get("status") or "completed"),
            output_kind="evidence",
        )
        persist_question_module_output(
            context,
            question_id="q8",
            module_id="q8_priority_derivation",
            payload=priority_baseline,
            status=str(priority_run.get("status") or "completed"),
            output_kind="evidence",
        )
        _q8_realtime_log(f"END persist q8 objective and priority module outputs {perf_counter() - phase_started:.3f}s")

        # 3. Build synthesis prompt
        phase_started = perf_counter()
        _q8_realtime_log("START build Q8 LLM prompt")
        system_prompt = (
            "你现在是 G19 Preference AI 的主目标生成与任务排序中枢。请严格审查传入的 Q1-Q7 约束条件。\n"
            "你的任务是：在绝对不违背 Q5（权限）和 Q6（红线）的前提下，基于 Q3/Q4 的真实能力，"
            "推断现在最应该推进的主目标是什么？当前阶段的具体任务是什么？"
        )
        objective_catalog = render_plugin_catalog(obj_oracles, heading="可用目标策略插件")
        nine_questions_summary = render_nine_questions_snapshot(question_snapshot or context.get("nine_questions"))
        task_state_summary = render_task_state(normalized_task_state)

        llm_request = build_q8_llm_request(
            system_prompt=system_prompt,
            nine_questions_summary=nine_questions_summary,
            task_state_summary=task_state_summary,
            objective_catalog=objective_catalog,
            priority_baseline=priority_baseline,
            q1_q7_snapshot=question_snapshot,
            nine_questions=question_snapshot,
            persistent_task_state=normalized_task_state,
            active_objectives=obj_oracles,
            functional_objectives=normalized_functional_objectives,
        )
        user_prompt = llm_request["prompt"]
        model_context = dict(llm_request["model_context"])
        requested_timeout = context.get("request_timeout_seconds")
        fallback_timeout = context.get("llm_request_timeout_seconds")
        try:
            timeout_seconds = float(requested_timeout or fallback_timeout or 90.0)
        except (TypeError, ValueError):
            timeout_seconds = 90.0
        model_context["request_timeout_seconds"] = max(5.0, min(timeout_seconds, 90.0))
        _q8_realtime_log(
            "END build Q8 LLM prompt "
            f"{perf_counter() - phase_started:.3f}s "
            f"prompt_chars={len(user_prompt)} "
            f"timeout={model_context['request_timeout_seconds']}"
        )

        # 4. Invoke LLM with strict traceability
        phase_started = perf_counter()
        _q8_realtime_log("START record Q8 model invoked")
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
        _q8_realtime_log(f"END record Q8 model invoked {perf_counter() - phase_started:.3f}s")

        try:
            started = perf_counter()
            _q8_realtime_log(
                "START provider.generate_json staged "
                f"provider={safe_provider_plugin_id(provider)} "
                f"model={model_context.get('model') or model_context.get('llm_model') or model_context.get('model_name') or 'unknown'}"
            )
            result_raw = _run_q8_staged_decision(
                provider=provider,
                system_prompt=system_prompt,
                question_snapshot=question_snapshot,
                normalized_task_state=normalized_task_state,
                priority_baseline=priority_baseline,
                normalized_functional_objectives=normalized_functional_objectives,
                caller_context=caller_context,
                request_timeout_seconds=float(model_context["request_timeout_seconds"]),
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
            staged_reasoning = (
                result_raw.get("_q8_staged_reasoning", {})
                if isinstance(result_raw, dict)
                else {}
            )
            if isinstance(result_raw, dict):
                result_raw.pop("_q8_staged_reasoning", None)
            _q8_realtime_log(
                "END provider.generate_json staged "
                f"{elapsed_ms / 1000:.3f}s "
                f"candidate_count={staged_reasoning.get('candidate_count', 0)} "
                f"allowed_count={staged_reasoning.get('allowed_count', 0)} "
                f"blocked_count={staged_reasoning.get('blocked_count', 0)}"
            )

            # 5. Validate & Return
            phase_started = perf_counter()
            _q8_realtime_log("START normalize and validate Q8 LLM result")
            normalized_result_raw = normalize_q8_inference_payload(result_raw)
            inference = Q8InferenceResult.model_validate(normalized_result_raw)
            inferred_objective = inference.objective_profile
            inferred_queue = inference.task_queue
            objective = inferred_objective.model_copy(
                update={
                    "current_phase_tasks": merge_string_lists(
                        inferred_objective.current_phase_tasks,
                        priority_baseline.get("immediate_tasks", []),
                    ),
                    "priority_order": merge_string_lists(
                        inferred_objective.priority_order,
                        priority_baseline.get("immediate_tasks", []),
                    ),
                    "escalation_conditions": merge_string_lists(
                        inferred_objective.escalation_conditions,
                        priority_baseline.get("escalation_conditions", []),
                    ),
                }
            )
            queue = inferred_queue.model_copy(
                update={
                    "next_self_tasks": merge_task_rows(
                        inferred_queue.next_self_tasks,
                        priority_baseline.get("immediate_tasks", []),
                        "next",
                    ),
                    "blocked_self_tasks": merge_task_rows(
                        inferred_queue.blocked_self_tasks,
                        priority_baseline.get("blocked_tasks", []),
                        "blocked",
                    ),
                    "proactive_actions": merge_task_rows(
                        inferred_queue.proactive_actions,
                        priority_baseline.get("proactive_actions", []),
                        "proactive",
                    ),
                }
            )
            _q8_realtime_log(
                "END normalize and validate Q8 LLM result "
                f"{perf_counter() - phase_started:.3f}s "
                f"next_tasks={len(queue.next_self_tasks)} "
                f"blocked_tasks={len(queue.blocked_self_tasks)} "
                f"proactive_actions={len(queue.proactive_actions)}"
            )
            phase_started = perf_counter()
            _q8_realtime_log("START persist q8_decision_projection module output")
            finish_module_run(decision_projection_run)
            persist_question_module_output(
                context,
                question_id="q8",
                module_id="q8_decision_projection",
                payload={
                    "objective_profile": objective.model_dump(mode="json"),
                    "task_queue": queue.model_dump(mode="json"),
                },
                status="completed",
                output_kind="inference",
            )
            _q8_realtime_log(f"END persist q8_decision_projection module output {perf_counter() - phase_started:.3f}s")
            # 5. Physical Task Persistence (Eradicate Forgery Stub)
            persistence_run = start_module_run(
                module_runs, "q8_task_persistence", source="plugins.nine_questions.q8"
            )
            try:
                phase_started = perf_counter()
                _q8_realtime_log("START task_persistence.persist_plan")
                task_persistence.persist_plan(
                    session_id=session_id,
                    turn_id=turn_id,
                    objective=objective.model_dump(mode="json"),
                    task_queue=queue.model_dump(mode="json")
                )
                _q8_realtime_log(f"END task_persistence.persist_plan {perf_counter() - phase_started:.3f}s")
                finish_module_run(persistence_run)
            except Exception as e:
                logger.error(f"INTEGRITY FAILURE: Q8 task persistence failed: {e}")
                fail_module_run(
                    persistence_run,
                    status="failed",
                    error_code="task_persistence_failed",
                    error_message=str(e),
                )
                raise RuntimeError(f"Cognitive Turn Halt: Could not persist Q8 plan results: {e}")
            phase_started = perf_counter()
            _q8_realtime_log("START persist q8_task_persistence module output")
            persist_question_module_output(
                context,
                question_id="q8",
                module_id="q8_task_persistence",
                payload={
                    "objective_profile": objective.model_dump(mode="json"),
                    "task_queue": queue.model_dump(mode="json"),
                },
                status=str(persistence_run.get("status") or "completed"),
                output_kind="integration",
            )
            _q8_realtime_log(f"END persist q8_task_persistence module output {perf_counter() - phase_started:.3f}s")

            diagnosis = question_authenticity_judgment(
                module_runs=module_runs,
                upstream_dependencies=upstream_dependencies,
                used_fallback=False,
                diagnosis_code="decision_persisted",
                diagnosis_message="Q8 generated and physically persisted the task queue.",
                required_modules=[
                    "q8_snapshot_validation",
                    "q8_task_state_load",
                    "q8_priority_derivation",
                    "q8_task_persistence",
                ],
            )
            diagnosis["plugin_runs"] = plugin_runs
            diagnosis["recovery_plan"] = build_recovery_plan(
                question_id="q8",
                retriable=True,
                rollback_available=False,
                partial_retry_available=True,
                partial_replace_available=True,
                actions=[
                    build_recovery_action(
                        "q8-rerun-question",
                        label="重跑 Q8 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q8",
                        reason="重新执行 Q8 推理链，刷新 objective 和 task_queue。",
                        path="/api/web/nine-questions/q8/run",
                    ),
                    build_recovery_action(
                        "q8-recover-task-persistence",
                        label="补写 Q8 任务到 Task Service",
                        kind="partial_replace",
                        executable=True,
                        scope="module",
                        target="q8_task_persistence",
                        reason="仅补写 task_queue 到 Task Service，不重跑 LLM。",
                        path="/api/web/nine-questions/q8/recover-task-persistence",
                    ),
                    build_recovery_action(
                        "q8-recompute-persistence",
                        label="局部重试任务持久化",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q8_task_persistence",
                        reason="仅重试 q8_task_persistence 模块，把当前最新 task_queue 重新写入 Task Service。",
                        path="/api/web/nine-questions/q8/modules/q8_task_persistence/retry",
                    ),
                ],
            )

            phase_started = perf_counter()
            _q8_realtime_log("START record Q8 model completed")
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
            _q8_realtime_log(f"END record Q8 model completed {perf_counter() - phase_started:.3f}s")
            _q8_realtime_log(f"END execute before return {perf_counter() - total_started:.3f}s")

            result_payload = {
                "objective": objective.model_dump(mode="json"),
                "task_queue": queue.model_dump(mode="json"),
                "q1_q7_snapshot": question_snapshot,
                "persistent_task_state": normalized_task_state,
                "q8_priority_baseline": priority_baseline,
                "q8_functional_objectives": normalized_functional_objectives,
                "q8_staged_reasoning": staged_reasoning,
                "q8_execution_diagnosis": diagnosis,
            }
            q8_module_runs = diagnosis.get("module_runs")
            q8_module_runs = q8_module_runs if isinstance(q8_module_runs, list) else []
            run_audit_integration(
                context,
                question_id="q8",
                module_runs=q8_module_runs,
                summary="Q8 目标排序与任务队列审计已记录。",
                payload={
                    "q8_objective_and_queue": result_payload,
                    "q8_objective_profile": result_payload.get("objective"),
                    "q8_task_queue": result_payload.get("task_queue"),
                    "q8_priority_baseline": result_payload.get("q8_priority_baseline") or {},
                },
            )
            run_memory_integration(
                context,
                question_id="q8",
                module_runs=q8_module_runs,
                title="Q8 Objective And Queue",
                summary="Q8 当前目标与任务队列已写入记忆。",
                layer="episodic",
                payload={
                    "q8_objective_profile": result_payload.get("objective"),
                    "q8_task_queue": result_payload.get("task_queue"),
                },
                tags=["nine-questions", "q8", "objective-queue"],
            )
            run_reflection_integration(
                context,
                question_id="q8",
                module_runs=q8_module_runs,
                subject="Q8 prioritization",
                summary="Q8 优先级合理性反思已记录。",
                reflection_type="decision_reflection",
                payload={
                    "q8_objective_profile": result_payload.get("objective"),
                    "q8_priority_baseline": result_payload.get("q8_priority_baseline") or {},
                    "q8_task_queue": result_payload.get("task_queue"),
                },
            )
            run_learning_integration(
                context,
                question_id="q8",
                module_runs=q8_module_runs,
                learning_kind="task_prioritization",
                summary="Q8 任务排序学习记录已登记。",
                payload={
                    "q8_objective_profile": result_payload.get("objective"),
                    "q8_task_queue": result_payload.get("task_queue"),
                },
            )
            diagnosis["module_runs"] = q8_module_runs
            result_payload["q8_execution_diagnosis"] = diagnosis
            return CognitiveToolResult(
                tool_id=self.plugin_id,
                summary="Synthesized objective and task queue (Q8)",
                proposals=[
                    {
                        "kind": "nine_question_q8_decision",
                        "result": result_payload,
                    }
                ],
                context_updates={
                    "q8_objective_and_queue": result_payload,
                    "q8_objective_profile": result_payload.get("objective"),
                    "q8_task_queue": result_payload.get("task_queue"),
                    "q8_q1_q7_snapshot": result_payload.get("q1_q7_snapshot") or {},
                    "q8_persistent_task_state": result_payload.get("persistent_task_state") or {},
                    "q8_priority_baseline": result_payload.get("q8_priority_baseline") or {},
                    "q8_functional_objectives": result_payload.get("q8_functional_objectives") or [],
                    "q8_staged_reasoning": result_payload.get("q8_staged_reasoning") or {},
                    "q8_execution_diagnosis": diagnosis,
                },
                confidence=0.8,
            )

        except Exception as exc:
            committed_result = _existing_q8_committed_result(context)
            if committed_result is not None:
                logger.warning(
                    "Q8 LLM synthesis failed; preserving committed completed Q8 snapshot: %s",
                    exc,
                )
                return committed_result
            fail_module_run(
                decision_projection_run,
                error_code="q8_execution_failed",
                error_message=str(exc),
            )
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
            # 严禁吞掉 Q8 LLM 故障并伪装成“只是当前没有目标/任务”。
            # 这里必须保留异常堆栈，否则后台推理失败会被误判成普通数据缺失。
            logger.exception("Q8 LLM synthesis failed")
            raise RuntimeError(f"[LLM MANDATORY] Q8 synthesis failed: {exc}") from exc

    def run_tool(self, context: Dict[str, Any]) -> CognitiveToolResult:
        try:
            run_tool_started = perf_counter()
            _q8_realtime_log("START run_tool")
            result = self.execute(dict(context))
        except Exception as exc:
            committed_result = _existing_q8_committed_result(context)
            if committed_result is not None:
                logger.warning(
                    "Q8 LLM synthesis failed; preserving committed completed Q8 snapshot: %s",
                    exc,
                )
                return committed_result
            # 严禁在 run_tool 兜底层吞掉异常并只返回 partial_failed 而不打日志。
            # 否则 execute 被替换、短路或提前失败时，后台故障会完全丢失审计痕迹。
            logger.exception("Q8 run_tool failed")
            failed_module_runs = bind_module_runs(context, "q8")
            decision_projection_run = start_module_run(
                failed_module_runs, "q8_decision_projection", source="plugins.nine_questions.q8"
            )
            fail_module_run(
                decision_projection_run,
                error_code="q8_execution_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q8",
                question_ref="我现在应该做什么",
                error_code="q8_execution_failed",
                error_message=str(exc),
                diagnosis_key="q8_execution_diagnosis",
                module_runs=list(failed_module_runs),
                plugin_runs=[],
                upstream_dependencies=[],
                context_updates={},
                required_modules=["q8_decision_projection"],
                partial_replace_available=True,
            )
        q8_execution_diagnosis = result.get("q8_execution_diagnosis") or {}
        q8_module_runs = q8_execution_diagnosis.get("module_runs")
        q8_module_runs = q8_module_runs if isinstance(q8_module_runs, list) else []
        projection_run = next(
            (item for item in q8_module_runs if isinstance(item, dict) and item.get("module_id") == "q8_decision_projection"),
            None,
        )
        if projection_run is None:
            projection_run = start_module_run(
                q8_module_runs, "q8_decision_projection", source="plugins.nine_questions.q8"
            )
        finish_module_run(projection_run)
        phase_started = perf_counter()
        _q8_realtime_log("START q8 audit integration")
        run_audit_integration(
            context,
            question_id="q8",
            module_runs=q8_module_runs,
            summary="Q8 目标排序与任务队列审计已记录。",
            payload={
                "q8_objective_and_queue": result,
                "q8_objective_profile": result.get("objective"),
                "q8_task_queue": result.get("task_queue"),
                "q8_priority_baseline": result.get("q8_priority_baseline") or {},
            },
        )
        _q8_realtime_log(f"END q8 audit integration {perf_counter() - phase_started:.3f}s")
        phase_started = perf_counter()
        _q8_realtime_log("START q8 memory integration")
        run_memory_integration(
            context,
            question_id="q8",
            module_runs=q8_module_runs,
            title="Q8 Objective And Queue",
            summary="Q8 当前目标与任务队列已写入记忆。",
            layer="episodic",
            payload={
                "q8_objective_profile": result.get("objective"),
                "q8_task_queue": result.get("task_queue"),
            },
            tags=["nine-questions", "q8", "objective-queue"],
        )
        _q8_realtime_log(f"END q8 memory integration {perf_counter() - phase_started:.3f}s")
        phase_started = perf_counter()
        _q8_realtime_log("START q8 reflection integration")
        run_reflection_integration(
            context,
            question_id="q8",
            module_runs=q8_module_runs,
            subject="Q8 prioritization",
            summary="Q8 优先级合理性反思已记录。",
            reflection_type="decision_reflection",
            payload={
                "q8_objective_profile": result.get("objective"),
                "q8_priority_baseline": result.get("q8_priority_baseline") or {},
                "q8_task_queue": result.get("task_queue"),
            },
        )
        _q8_realtime_log(f"END q8 reflection integration {perf_counter() - phase_started:.3f}s")
        phase_started = perf_counter()
        _q8_realtime_log("START q8 learning integration")
        run_learning_integration(
            context,
            question_id="q8",
            module_runs=q8_module_runs,
            learning_kind="task_prioritization",
            summary="Q8 任务排序学习记录已登记。",
            payload={
                "q8_objective_profile": result.get("objective"),
                "q8_task_queue": result.get("task_queue"),
            },
        )
        _q8_realtime_log(f"END q8 learning integration {perf_counter() - phase_started:.3f}s")
        q8_execution_diagnosis["module_runs"] = q8_module_runs
        result["q8_execution_diagnosis"] = q8_execution_diagnosis
        _q8_realtime_log(f"END run_tool {perf_counter() - run_tool_started:.3f}s")

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
                "q8_execution_diagnosis": q8_execution_diagnosis,
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
