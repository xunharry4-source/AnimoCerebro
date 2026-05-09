import logging
import json
import re
from copy import deepcopy
from time import perf_counter
from typing import Any, Dict, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q2_asset_inventory.service import (
    load_external_public_output as load_q2_external_public_output,
    load_internal_public_output as load_q2_internal_public_output,
)
from plugins.nine_questions.q1_where_am_i.service import (
    load_public_output as load_q1_public_output,
)
from plugins.nine_questions.q3_role_inference.service import (
    load_public_output as load_q3_public_output,
)
from plugins.nine_questions.q7_what_else_can_i_do.service import (
    load_external_public_output as load_q7_external_public_output,
    load_internal_public_output as load_q7_internal_public_output,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.plugin_ids import NINE_QUESTION_Q8
from zentex.plugins.models import PluginLifecycleStatus

from plugins.nine_questions.q8_what_should_i_do_now.models import (
    Q8InferenceResult,
)
from plugins.nine_questions.q8_what_should_i_do_now.internal_tasks import (
    run_q8_internal_task_generation,
)
from plugins.nine_questions.q8_what_should_i_do_now.external_tasks import (
    run_q8_external_task_generation,
)
from plugins.nine_questions.q8_what_should_i_do_now.modules import (
    derive_priority_baseline,
    merge_string_lists,
    normalize_functional_objectives,
    normalize_snapshot_dict,
    normalize_task_state,
)
from zentex.nine_questions.q8_q9_boundary import validate_q8_output_boundary

logger = logging.getLogger(__name__)


def _q8_realtime_log(message: str) -> None:
    logger.info("[Q8Plugin] %s", message)


from zentex.common.nine_questions_shared import (
    bind_module_runs,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    build_question_dependency,
    fail_module_run,
    json_safe_payload,
    record_plugin_attempt,
    record_plugin_result,
    record_model_failed,
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


def _q8_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _q8_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    normalized: list[Any] = []
    for item in value:
        if item in (None, "", [], {}):
            continue
        if isinstance(item, dict):
            compact = {
                str(key): _q8_text(val)
                for key, val in item.items()
                if val not in (None, "", [], {})
            }
            if compact:
                normalized.append(compact)
        else:
            normalized.append(_q8_text(item))
    return normalized


def _q8_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _q8_text(item))]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [item_text for item in parsed if (item_text := _q8_text(item))]
        return [
            cleaned
            for line in text.splitlines()
            if (cleaned := re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip())
        ]
    return []


def _resolve_workspace_task_goals(context: dict[str, Any]) -> list[str]:
    direct = _q8_string_list(
        context.get("workspace_task_goals")
        or context.get("settings_task_goals")
        or context.get("task_goals")
    )
    if direct:
        return list(dict.fromkeys(direct))

    workspace_store = context.get("workspace_store")
    if workspace_store is None:
        return []

    workspace = None
    get_by_path = getattr(workspace_store, "get_workspace_by_path", None)
    if callable(get_by_path):
        for key in ("workspace_path", "workspace"):
            workspace_path = _q8_text(context.get(key))
            if not workspace_path:
                continue
            try:
                workspace = get_by_path(workspace_path)
            except Exception:
                workspace = None
            if workspace is not None:
                break

    if workspace is None:
        get_default = getattr(workspace_store, "get_default_workspace", None)
        if callable(get_default):
            try:
                workspace = get_default()
            except Exception:
                workspace = None

    if workspace is None:
        return []
    return list(dict.fromkeys(_q8_string_list(getattr(workspace, "task_goals", None))))


def _apply_configured_extra_goals_to_priority_baseline(
    priority_baseline: dict[str, Any],
    configured_extra_goals: list[str],
) -> dict[str, Any]:
    if not configured_extra_goals:
        return dict(priority_baseline)
    return {
        **priority_baseline,
        "configured_extra_goals": configured_extra_goals,
        "immediate_tasks": merge_string_lists(
            [
                f"pursue configured extra brain goal: {goal}"
                for goal in configured_extra_goals
            ],
            priority_baseline.get("immediate_tasks", []),
        ),
        "proactive_actions": merge_string_lists(
            [
                f"keep configured extra brain goal in Q8 synthesis: {goal}"
                for goal in configured_extra_goals
            ],
            priority_baseline.get("proactive_actions", []),
        ),
    }


def _q8_meaningful_redline_items(value: Any) -> list[str]:
    empty_markers = (
        "无",
        "暂无",
        "未发现",
        "未命中",
        "没有",
        "none",
        "n/a",
        "no current",
        "no active",
        "not found",
    )
    items = _q8_list(value)
    normalized: list[str] = []
    for item in items:
        text = str(item or "").strip()
        lowered = text.lower()
        if not text:
            continue
        if any(lowered.startswith(marker) for marker in empty_markers):
            continue
        normalized.append(text)
    return normalized


def _q8_q7_active_redline_gate(q7_snapshot: dict[str, Any]) -> dict[str, Any]:
    q7_root = _q8_dict(q7_snapshot.get("RedLineAssessment") or q7_snapshot)
    hits = _q8_meaningful_redline_items(q7_root.get("current_redline_hits") or q7_root.get("current_red_line_hits"))
    rejected = _q8_meaningful_redline_items(q7_root.get("rejected_operations_log") or q7_root.get("rejected_operation_records"))
    constraints = _q8_list(q7_root.get("non_bypassable_constraints"))
    active = bool(hits)
    return {
        "active": active,
        "hits": hits,
        "rejected_operation_records": rejected,
        "non_bypassable_constraints": constraints,
        "reason": (
            "Q7 reported active red-line hits; Q8 must convert external tasking into internal cognitive preflight."
            if active
            else ""
        ),
    }


def _q8_diagnosis_status(payload: dict[str, Any], key: str) -> str:
    diagnosis = _q8_dict(payload.get(key))
    return _q8_text(diagnosis.get("authenticity_status") or payload.get("status"))


def _load_q8_upstream_llm_outputs(context: dict[str, Any]) -> dict[str, Any]:
    """Single Q8 source for upstream LLM outputs.

    Q8 must not mix context snapshots, raw traces, or direct table reads from
    multiple call sites. This function is the only Q8 entrypoint that calls
    upstream-owned LLM output accessors.
    """
    state_db_path = context.get("nine_question_state_db_path")
    q7_internal_llm_output = load_q7_internal_public_output(db_path=state_db_path)
    q7_external_llm_output = load_q7_external_public_output(db_path=state_db_path)
    return normalize_snapshot_dict(
        {
            "q1": load_q1_public_output(db_path=state_db_path),
            "q2": {
                "internal_tool_llm_output": load_q2_internal_public_output(db_path=state_db_path),
                "external_tool_llm_output": load_q2_external_public_output(db_path=state_db_path),
            },
            "q3": load_q3_public_output(db_path=state_db_path),
            "q7": {
                "internal_creative_possibility_set": q7_internal_llm_output,
                "internal_redline_llm_output": q7_internal_llm_output,
                "external_redline_llm_output": q7_external_llm_output,
            },
        }
    )


def _build_q8_decision_digest(snapshot: dict[str, Any]) -> dict[str, Any]:
    q1 = _q8_dict(snapshot.get("q1"))
    q2 = _q8_dict(snapshot.get("q2"))
    q3 = _q8_dict(snapshot.get("q3"))
    q7 = _q8_dict(snapshot.get("q7"))

    q1_scene = _q8_dict(q1.get("q1_scene_model") or q1.get("workspace_domain_inference"))
    q1_env = _q8_dict(q1.get("environment_event") or q1.get("physical_host_state"))
    q2_internal_output = _q8_dict(q2.get("internal_tool_llm_output"))
    q2_external_output = _q8_dict(q2.get("external_tool_llm_output"))
    q2_internal_tools = _q8_list(q2_internal_output.get("internal_cognitive_tools")) + _q8_list(
        q2_internal_output.get("internal_functional_plugins"),
    )
    q2_external_tools = _q8_list(q2_external_output.get("available_external_tools"))
    q3_role = _q8_dict(q3.get("q3_role_profile") or q3.get("identity_kernel_snapshot"))
    q3_mission = _q8_dict(q3.get("q3_mission_boundary") or q3.get("mission_continuity_projection"))
    q7_internal_output = _q8_dict(q7.get("internal_creative_possibility_set"))
    q7_external_output = _q8_dict(q7.get("external_redline_llm_output"))
    q7_profile = _q8_dict(
        q7_external_output.get("Q7ExternalRedLineAssessment")
        or q7_external_output.get("ExternalRedLineAssessment")
        or q7_external_output.get("RedLineAssessment")
        or q7.get("q7_red_line_assessment")
        or q7.get("red_line_assessment")
        or q7
    )
    q7_profile = _q8_dict(q7_profile.get("RedLineAssessment") or q7_profile)

    return {
        "q1": {
            "status": _q8_diagnosis_status(q1, "q1_execution_diagnosis"),
            "environment_summary": _q8_text(q1.get("summary") or q1_env.get("summary")),
            "primary_domain": _q8_text(q1_scene.get("primary_domain")),
            "secondary_domains": _q8_list(q1_scene.get("secondary_domains")),
            "suggested_first_step": _q8_text(q1_scene.get("suggested_first_step")),
            "uncertainty": _q8_dict(q1.get("q1_uncertainty_profile")),
        },
        "q2": {
            "status": "completed",
            "resource_status": "",
            "bottleneck_node": "",
            "missing_critical_assets": [],
            "available_cognitive_tools": q2_internal_tools,
            "available_execution_tools": q2_external_tools,
            "functional_plugins": _q8_list(q2_internal_output.get("internal_functional_plugins")),
            "cognitive_plugins": _q8_list(q2_internal_output.get("internal_cognitive_tools")),
            "accessible_workspace_zones": [],
        },
        "q3": {
            "status": _q8_diagnosis_status(q3, "q3_execution_diagnosis"),
            "role_profile": {
                "identity_role": _q8_text(q3_role.get("identity_role")),
                "active_role": _q8_text(q3_role.get("active_role")),
                "inferred_reference_role": _q8_text(q3_role.get("inferred_reference_role")),
                "role_alignment_gap": _q8_text(q3_role.get("role_alignment_gap")),
                "task_role": _q8_text(q3_role.get("task_role")),
            },
            "mission": {
                "current_mission": _q8_text(q3_mission.get("current_mission")),
                "priority_duties": _q8_list(q3_mission.get("priority_duties")),
                "continuity_boundaries": _q8_list(q3_mission.get("continuity_boundaries")),
            },
        },
        "q7": {
            "status": _q8_diagnosis_status(q7, "q7_execution_diagnosis"),
            "current_red_line_hits": _q8_list(q7_profile.get("current_redline_hits") or q7_profile.get("current_red_line_hits")),
            "rejected_operation_records": _q8_list(q7_profile.get("rejected_operations_log") or q7_profile.get("rejected_operation_records")),
            "ban_source_explanations": _q8_list(q7_profile.get("ban_source_explanations") or q7_profile.get("constraint_sources_explanation")),
            "non_bypassable_constraints": _q8_list(
                q7_profile.get("non_bypassable_constraints") or q7.get("q7_non_bypassable_constraints"),
            ),
            "question_driver_refs": _q8_list(q7_profile.get("question_driver_refs") or q7.get("q7_question_driver_refs")),
            "internal_creative_possibilities": _q8_list(
                q7_internal_output.get("creative_possibilities") or q7.get("q7_internal_creative_possibilities")
            ),
            "internal_possibility_statuses": _q8_list(
                q7_internal_output.get("possibility_statuses") or q7.get("q7_internal_possibility_statuses")
            ),
            "external_creative_possibilities": _q8_list(
                q7_external_output.get("creative_possibilities") or q7.get("q7_external_creative_possibilities")
            ),
            "external_possibility_statuses": _q8_list(
                q7_external_output.get("possibility_statuses") or q7.get("q7_external_possibility_statuses")
            ),
        },
    }


def _q8_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_q8_llm_output_payload(result_payload: dict[str, Any]) -> dict[str, Any]:
    """Root Q8 is an orchestrator; branch LLM I/O stays in branch modules."""
    return {
        "q8_objective_profile": result_payload.get("objective") or {},
        "q8_task_queue": result_payload.get("task_queue") or {},
    }


def _q8_public_task_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allowed_keys = {
        "task_id",
        "id",
        "title",
        "task",
        "status",
        "reason",
        "priority",
        "task_scope",
        "executor_type",
        "target_id",
        "required_capability",
        "creation_rationale",
        "task_goal",
        "completion_condition",
        "metadata",
    }
    for index, item in enumerate(value if isinstance(value, list) else []):
        if isinstance(item, dict):
            title = _q8_text(item.get("title") or item.get("task") or item.get("intent_name") or item.get("objective"))
            if not title:
                continue
            row = {
                str(key): json_safe_payload(val)
                for key, val in item.items()
                if key in allowed_keys and val not in (None, "", [], {})
            }
            row["title"] = title
            row.setdefault("task_id", _q8_text(item.get("task_id") or item.get("id") or f"q8-task-{index}"))
            rows.append(row)
            continue
        text = _q8_text(item)
        if text:
            rows.append({"task_id": f"q8-task-{index}", "title": text})
    return rows


def _q8_public_task_queue(value: Any) -> dict[str, list[dict[str, Any]]]:
    queue = _q8_dict(value)
    return {
        "next_self_tasks": _q8_public_task_rows(queue.get("next_self_tasks")),
        "blocked_self_tasks": _q8_public_task_rows(queue.get("blocked_self_tasks")),
        "proactive_actions": _q8_public_task_rows(queue.get("proactive_actions")),
    }


def _q8_merge_rows_with_upstream(rows: list[dict[str, Any]], upstream_public_output: dict[str, Any]) -> list[dict[str, Any]]:
    upstream_items = _q8_list(upstream_public_output.get("creative_possibilities"))
    upstream_map = {
        _q8_text(item.get("objective_number")): item
        for item in upstream_items
        if isinstance(item, dict) and _q8_text(item.get("objective_number"))
    }
    merged: list[dict[str, Any]] = []
    for row in rows:
        objective_number = _q8_text(row.get("objective_number") or row.get("target_id"))
        if objective_number and objective_number in upstream_map:
            merged.append({**upstream_map[objective_number], **row})
        else:
            merged.append(row)
    return merged


def _q8_public_objective_profile(value: Any) -> dict[str, Any]:
    objective = _q8_dict(value)
    return {
        "current_mission": _q8_text(objective.get("current_mission") or objective.get("current_primary_objective")),
        "mission_rationale": _q8_text(objective.get("mission_rationale")),
        "primary_objectives": _q8_string_list(objective.get("primary_objectives")),
        "secondary_objectives": _q8_string_list(objective.get("secondary_objectives")),
        "completion_conditions": _q8_string_list(objective.get("completion_conditions")),
        "pause_conditions": _q8_string_list(objective.get("pause_conditions")),
        "escalation_conditions": _q8_string_list(objective.get("escalation_conditions")),
        "current_phase_tasks": _q8_string_list(objective.get("current_phase_tasks")),
        "priority_order": _q8_string_list(objective.get("priority_order")),
    }


def _q8_branch_public_output(
    *,
    scope: str,
    task_result: dict[str, Any],
    upstream_q7_public_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inference_payload = _q8_dict(task_result.get("inference_payload"))
    objective_profile = _q8_public_objective_profile(inference_payload.get("objective_profile"))
    task_queue = _q8_public_task_queue(inference_payload.get("task_queue"))
    task_plan = _q8_dict(task_result.get("task_plan"))
    generated = _q8_public_task_rows(task_plan.get("generated") or task_result.get("tasks"))
    upstream_public = _q8_dict(upstream_q7_public_output)
    if upstream_public:
        generated = _q8_merge_rows_with_upstream(generated, upstream_public)
    public_output = {
        "scope": scope,
        "objective_profile": objective_profile,
        "task_queue": task_queue,
        "task_plan": {
            "planner": _q8_text(task_plan.get("planner")) or f"q8_{scope}_task_generation",
            "generated": generated,
        },
    }
    if upstream_public:
        public_output["upstream_q7_public_output"] = deepcopy(upstream_public)
    meaningful = (
        objective_profile.get("current_mission")
        or objective_profile.get("primary_objectives")
        or objective_profile.get("priority_order")
        or generated
        or any(task_queue.values())
    )
    if not meaningful:
        raise RuntimeError(f"q8_{scope}_public_output_empty")
    return public_output


def _merge_q8_public_branch_outputs(
    *,
    internal_output: dict[str, Any],
    external_output: dict[str, Any],
    fallback_mission: str,
) -> dict[str, Any]:
    internal_objective = _q8_dict(internal_output.get("objective_profile"))
    external_objective = _q8_dict(external_output.get("objective_profile"))
    internal_queue = _q8_public_task_queue(internal_output.get("task_queue"))
    external_queue = _q8_public_task_queue(external_output.get("task_queue"))
    current_mission = (
        _q8_text(internal_objective.get("current_mission"))
        or _q8_text(external_objective.get("current_mission"))
        or fallback_mission
    )
    return {
        "objective_profile": {
            "current_mission": current_mission,
            "mission_rationale": _q8_text(internal_objective.get("mission_rationale"))
            or _q8_text(external_objective.get("mission_rationale")),
            "primary_objectives": merge_string_lists(
                _q8_string_list(internal_objective.get("primary_objectives")),
                _q8_string_list(external_objective.get("primary_objectives")),
            ) or ([current_mission] if current_mission else []),
            "secondary_objectives": merge_string_lists(
                _q8_string_list(internal_objective.get("secondary_objectives")),
                _q8_string_list(external_objective.get("secondary_objectives")),
            ),
            "completion_conditions": merge_string_lists(
                _q8_string_list(internal_objective.get("completion_conditions")),
                _q8_string_list(external_objective.get("completion_conditions")),
            ),
            "pause_conditions": merge_string_lists(
                _q8_string_list(internal_objective.get("pause_conditions")),
                _q8_string_list(external_objective.get("pause_conditions")),
            ),
            "escalation_conditions": merge_string_lists(
                _q8_string_list(internal_objective.get("escalation_conditions")),
                _q8_string_list(external_objective.get("escalation_conditions")),
            ),
            "current_phase_tasks": merge_string_lists(
                _q8_string_list(internal_objective.get("current_phase_tasks")),
                _q8_string_list(external_objective.get("current_phase_tasks")),
            ),
            "priority_order": merge_string_lists(
                _q8_string_list(internal_objective.get("priority_order")),
                _q8_string_list(external_objective.get("priority_order")),
            ) or ([current_mission] if current_mission else []),
        },
        "task_queue": {
            "next_self_tasks": internal_queue["next_self_tasks"] + external_queue["next_self_tasks"],
            "blocked_self_tasks": internal_queue["blocked_self_tasks"] + external_queue["blocked_self_tasks"],
            "proactive_actions": internal_queue["proactive_actions"] + external_queue["proactive_actions"],
        },
    }


def _q8_current_mission_from_q3(question_snapshot: dict[str, Any]) -> str:
    q3 = _q8_dict(question_snapshot.get("q3"))
    mission = _q8_dict(q3.get("mission"))
    for value in (
        mission.get("current_mission"),
        q3.get("current_mission"),
        q3.get("summary"),
    ):
        text = _q8_text(value)
        if text:
            return text
    raise RuntimeError("Q8 requires Q3 MissionContinuityBoundary.current_mission before objective synthesis.")


class WhatShouldIDoNowPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    """
    [LLM MANDATORY] Q8 Phase Plugin.
    Synopsizes Q1/Q2/Q3/Q7 to generate the current focus and task queue.
    The core decision hub for the Zentex autonomous controller.
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
    purpose: str = "Synthesize current primary objective and task queue under Q1/Q2/Q3/Q7 constraints."
    input_schema: Dict[str, Any] = {"type": "object"}
    output_schema: Dict[str, Any] = {"type": "object"}
    required_context: List[str] = ["nine_questions", "persistent_task_state", "plugin_service", "transcript_store", "llm_service"]
    trigger_conditions: List[str] = ["inspection", "always"]
    do_not_use_when: List[str] = ["missing_llm_service"]
    read_only: bool = True
    side_effect_free: bool = True
    is_default_version: bool = True
    is_official_release: bool = True

    def build_internal_public_output(
        self,
        internal_task_result: dict[str, Any],
        upstream_q7_public_output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _q8_branch_public_output(
            scope="internal",
            task_result=internal_task_result,
            upstream_q7_public_output=upstream_q7_public_output,
        )

    def build_external_public_output(
        self,
        external_task_result: dict[str, Any],
        upstream_q7_public_output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _q8_branch_public_output(
            scope="external",
            task_result=external_task_result,
            upstream_q7_public_output=upstream_q7_public_output,
        )

    def execute(self, context: Dict[str, Any], trace_id: str = "") -> Dict[str, Any]:
        """
        Synthesize current primary objective and tasks.
        """
        context = dict(context)
        if trace_id and not context.get("trace_id"):
            context["trace_id"] = trace_id
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
        _q8_realtime_log("START load upstream LLM outputs via upstream accessors")
        raw_question_snapshot = _load_q8_upstream_llm_outputs(context)
        question_snapshot = _build_q8_decision_digest(raw_question_snapshot)
        _q8_realtime_log(
            "END load upstream LLM outputs via upstream accessors "
            f"{perf_counter() - phase_started:.3f}s keys={sorted(question_snapshot.keys())}"
        )
        snapshot_validation_run = start_module_run(
            module_runs, "q8_snapshot_validation", source="plugins.nine_questions.q8"
        )
        for dependency_id in ("q1", "q2", "q3", "q7"):
            upstream_dependencies.append(
                build_question_dependency(
                    dependency_id,
                    payload=raw_question_snapshot.get(dependency_id),
                    required=True,
                )
            )
        invalid_dependencies = [
            item
            for item in upstream_dependencies
            if item["required"] and item["status"] != "completed"
        ]
        if invalid_dependencies:
            fail_module_run(
                snapshot_validation_run,
                status="failed",
                error_code="upstream_dependency_invalid",
                error_message=f"Q8 requires completed upstream Q1/Q2/Q3/Q7 LLM outputs: {invalid_dependencies}",
            )
            raise RuntimeError(
                f"Q8 requires completed upstream Q1/Q2/Q3/Q7 LLM outputs: {invalid_dependencies}"
            )
        finish_module_run(snapshot_validation_run)

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
        finish_module_run(task_state_load_run)
        
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
        if plugin_service is None:
            fail_module_run(
                objective_chain_run,
                status="failed",
                error_code="plugin_service_missing",
                error_message="Q8 functional objective chain was not started because plugin_service is missing.",
            )
            raise RuntimeError("Q8 requires plugin_service for functional objective execution.")
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
            if item.get("status") != "done":
                record_plugin_result(
                    run,
                    status="failed",
                    error_code="functional_objective_failed",
                    error_message=str(item.get("error") or item.get("status") or "functional plugin failed"),
                )
                fail_module_run(
                    objective_chain_run,
                    status="failed",
                    error_code="functional_objective_failed",
                    error_message=str(item.get("error") or item.get("status") or "functional plugin failed"),
                )
                raise RuntimeError("Q8 functional objective plugin failed; refusing incomplete synthesis.")
            record_plugin_result(
                run,
                status="completed",
                output_summary={
                    "result_keys": sorted((item.get("result") or {}).keys())
                    if isinstance(item.get("result"), dict)
                    else []
                },
            )
        obj_oracles = [
            str(item.get("plugin_id") or "")
            for item in functional_objectives
            if item.get("status") == "done"
        ]
        if not obj_oracles:
            fail_module_run(
                objective_chain_run,
                status="failed",
                error_code="functional_objective_missing",
                error_message="Q8 requires at least one successful objective plugin result.",
            )
            raise RuntimeError("Q8 requires at least one successful objective plugin result.")
        finish_module_run(objective_chain_run)
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
        configured_extra_goals = _resolve_workspace_task_goals(context)
        priority_baseline = _apply_configured_extra_goals_to_priority_baseline(
            priority_baseline,
            configured_extra_goals,
        )
        priority_baseline = {
            **priority_baseline,
            "priority_factors": [
                {"factor": "q7_constraint_pressure", "count": len(question_snapshot.get("q7", {}).get("non_bypassable_constraints", []) or [])},
                {"factor": "resource_gap_pressure", "count": len(question_snapshot.get("q3", {}).get("missing_critical_assets", []) or [])},
                {"factor": "active_task_pressure", "count": sum(len(v) for v in normalized_task_state.values())},
                {"factor": "configured_extra_goal_pressure", "count": len(configured_extra_goals)},
            ],
        }
        _q8_realtime_log(
            "END normalize functional objectives and derive priority baseline "
            f"{perf_counter() - phase_started:.3f}s "
            f"objectives={len(normalized_functional_objectives)} "
            f"immediate_tasks={len(priority_baseline.get('immediate_tasks', []) or [])}"
        )
        finish_module_run(priority_run)

        # 3. Prepare the shared upstream state. The internal/external modules own
        # their own parameter construction, LLM calls, scoped logs, and scoped saves.
        redline_gate = _q8_q7_active_redline_gate(_q8_dict(question_snapshot.get("q7")))
        if redline_gate.get("active"):
            priority_baseline = {
                **priority_baseline,
                "immediate_tasks": merge_string_lists(
                    [
                        "perform internal Q7 red-line preflight before any external action",
                        "generate a resource negotiation request for the blocked external action",
                        "run self-rehearsal under non-bypassable constraints",
                    ],
                    priority_baseline.get("immediate_tasks", []),
                ),
                "blocked_tasks": merge_string_lists(
                    priority_baseline.get("blocked_tasks", []),
                    [
                        "external tasking blocked by Q7 active red-line assessment",
                    ],
                ),
                "q7_redline_downgrade": redline_gate,
            }
        requested_timeout = context.get("request_timeout_seconds")
        configured_timeout = context.get("llm_request_timeout_seconds")
        try:
            timeout_seconds = float(requested_timeout or configured_timeout or 90.0)
        except (TypeError, ValueError):
            timeout_seconds = 90.0
        request_timeout_seconds = max(5.0, min(timeout_seconds, 540.0))
        failure_caller_context = build_caller_context(
            invocation_phase="nine_question_q8_task_module_orchestration",
            source_module="q8_what_should_i_do_now_plugin",
            question_ref="我现在应该做什么",
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        try:
            started = perf_counter()
            phase_started = perf_counter()
            _q8_realtime_log("START internal_tasks module")
            internal_task_result = run_q8_internal_task_generation(
                context=context,
                provider=provider,
                transcript_store=transcript_store,
                module_runs=module_runs,
                question_snapshot=question_snapshot,
                priority_baseline=priority_baseline,
                normalized_task_state=normalized_task_state,
                request_timeout_seconds=request_timeout_seconds,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                decision_id=decision_id,
                request_id=request_id,
            )
            _q8_realtime_log(f"END internal_tasks module {perf_counter() - phase_started:.3f}s")

            phase_started = perf_counter()
            _q8_realtime_log("START external_tasks module")
            external_task_result = run_q8_external_task_generation(
                context=context,
                provider=provider,
                transcript_store=transcript_store,
                module_runs=module_runs,
                question_snapshot=question_snapshot,
                priority_baseline=priority_baseline,
                normalized_task_state=normalized_task_state,
                request_timeout_seconds=request_timeout_seconds,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                decision_id=decision_id,
                request_id=request_id,
            )
            _q8_realtime_log(f"END external_tasks module {perf_counter() - phase_started:.3f}s")

            elapsed_ms = int((perf_counter() - started) * 1000)
            internal_cognitive_tasks = list(internal_task_result.get("tasks") or [])
            external_execution_tasks = list(external_task_result.get("tasks") or [])
            q3_current_mission = _q8_current_mission_from_q3(question_snapshot)
            q7_public_snapshot = _q8_dict(raw_question_snapshot.get("q7"))
            internal_public_output = self.build_internal_public_output(
                internal_task_result,
                _q8_dict(q7_public_snapshot.get("internal_creative_possibility_set")),
            )
            external_public_output = self.build_external_public_output(
                external_task_result,
                _q8_dict(q7_public_snapshot.get("external_redline_llm_output")),
            )
            result_raw = _merge_q8_public_branch_outputs(
                internal_output=internal_public_output,
                external_output=external_public_output,
                fallback_mission=q3_current_mission,
            )
            validate_q8_output_boundary(result_raw)
            staged_reasoning = {
                "execution_order": ["internal_tasks", "external_tasks"],
                "q7_redline_gate": redline_gate,
                "request_timeout_seconds": request_timeout_seconds,
                "internal": internal_task_result.get("reasoning") or {},
                "external": external_task_result.get("reasoning") or {},
            }

            # 5. Validate & Return
            phase_started = perf_counter()
            _q8_realtime_log("START validate Q8 module orchestration result")
            inference = Q8InferenceResult.model_validate(result_raw)
            inferred_objective = inference.objective_profile
            inferred_queue = inference.task_queue
            objective = inferred_objective
            queue = inferred_queue
            separated_task_plan = {
                "internal": internal_public_output["task_plan"],
                "external": external_public_output["task_plan"],
            }
            _q8_realtime_log(
                "END validate Q8 module orchestration result "
                f"{perf_counter() - phase_started:.3f}s "
                f"internal_tasks={len(internal_cognitive_tasks)} "
                f"external_tasks={len(external_execution_tasks)}"
            )
            finish_module_run(decision_projection_run)

            diagnosis = {
                "authenticity_status": "completed",
                "diagnosis_code": "abstract_intent_generated",
                "diagnosis_message": "Q8 generated pure abstract task intents.",
                "module_runs": module_runs,
                "upstream_dependencies": upstream_dependencies,
            }
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
                ],
            )

            phase_started = perf_counter()
            _q8_realtime_log("START assemble Q8 module trace index")
            internal_trace_payload = _q8_dict(internal_task_result.get("trace_payload"))
            external_trace_payload = _q8_dict(external_task_result.get("trace_payload"))
            trace_invocations = [
                item
                for item in (internal_trace_payload, external_trace_payload)
                if isinstance(item, dict) and item
            ]
            primary_trace = dict(trace_invocations[-1]) if trace_invocations else {}
            llm_trace_payload = {
                "request_id": request_id,
                "decision_id": decision_id,
                "provider_name": primary_trace.get("provider_name"),
                "model": primary_trace.get("model"),
                "source_module": "q8_what_should_i_do_now_plugin",
                "invocation_phase": "nine_question_q8_task_module_orchestration",
                "question_driver_refs": primary_trace.get("question_driver_refs"),
                "invocations": trace_invocations,
                "elapsed_ms": elapsed_ms,
            }
            _q8_realtime_log(f"END assemble Q8 module trace index {perf_counter() - phase_started:.3f}s")
            _q8_realtime_log(f"END execute before return {perf_counter() - total_started:.3f}s")

            result_payload = {
                "objective": objective.model_dump(mode="json"),
                "task_queue": queue.model_dump(mode="json"),
                "q8_internal_result": internal_public_output,
                "q8_external_result": external_public_output,
                "q8_separated_task_plan": {
                    "internal": {
                        "generated": separated_task_plan["internal"]["generated"],
                        "planner": separated_task_plan["internal"]["planner"],
                    },
                    "external": {
                        "generated": separated_task_plan["external"]["generated"],
                        "planner": separated_task_plan["external"]["planner"],
                    },
                },
                "q8_execution_diagnosis": diagnosis,
            }
            q8_module_runs = diagnosis.get("module_runs")
            q8_module_runs = q8_module_runs if isinstance(q8_module_runs, list) else []
            diagnosis["module_runs"] = q8_module_runs
            result_payload["q8_execution_diagnosis"] = diagnosis
            q8_llm_output_payload = _build_q8_llm_output_payload(result_payload)
            return CognitiveToolResult(
                tool_id=self.plugin_id,
                summary="Synthesized objective and task queue (Q8)",
                llm_output=q8_llm_output_payload,
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
                    "q8_internal_result": internal_public_output,
                    "q8_external_result": external_public_output,
                    "q8_separated_task_plan": result_payload.get("q8_separated_task_plan") or {},
                    "q8_execution_diagnosis": diagnosis,
                    "llm_trace_payload": llm_trace_payload,
                },
                llm_trace_payload=llm_trace_payload,
                confidence=0.8,
            )

        except Exception as exc:
            raw_response_on_error = json_safe_payload(getattr(provider, "last_raw_response", None))
            token_usage_on_error = json_safe_payload(getattr(provider, "last_token_usage", None))
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
                    "caller_context": failure_caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                    "raw_response": raw_response_on_error,
                    "token_usage": token_usage_on_error,
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
            logger.exception("Q8 run_tool failed")
            raise RuntimeError(f"[LLM MANDATORY] Q8 run_tool failed: {exc}") from exc
        if isinstance(result, CognitiveToolResult):
            return result
        llm_trace_payload = _q8_dict(result.get("llm_trace_payload"))
        q8_execution_diagnosis = _q8_dict(result.get("q8_execution_diagnosis"))
        q8_llm_output_payload = _build_q8_llm_output_payload(result)
        _q8_realtime_log(f"END run_tool {perf_counter() - run_tool_started:.3f}s")

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Synthesized objective and task queue (Q8)",
            llm_output=q8_llm_output_payload,
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
                "q8_internal_result": result.get("q8_internal_result") or {},
                "q8_external_result": result.get("q8_external_result") or {},
                "q8_separated_task_plan": result.get("q8_separated_task_plan") or {},
                "q8_execution_diagnosis": q8_execution_diagnosis,
                "llm_trace_payload": llm_trace_payload,
            },
            llm_trace_payload=llm_trace_payload,
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
