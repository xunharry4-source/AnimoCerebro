"""Common Nine-Questions Service Layer

Provides shared utilities for:
- Session management (get/create)
- State management (get/update)
- Question report building
- Common error handling
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request

from zentex.web_console.dependencies import (
    get_session_manager,
    get_nine_question_state_manager,
    get_kernel_service_facade,
)
from zentex.web_console.contracts.nine_questions import NineQuestionReportItem
from .evidence_q1 import _extract_q1_llm_upgrade
from .q_handlers import QUESTION_HANDLERS

logger = logging.getLogger(__name__)

EXPECTED_QUESTION_IDS = tuple(f"q{i}" for i in range(1, 10))


def _build_missing_snapshot(
    question_id: str,
    snapshot_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary = f"{QUESTION_TITLES.get(question_id, question_id)} 尚无快照记录"
    context_updates: dict[str, Any] = {
        "snapshot_status": "missing",
        "missing_question_id": question_id,
    }
    if question_id == "q8":
        context_updates["q1_q7_snapshot"] = _build_question_dependency_snapshot(
            snapshot_map or {},
            upto_question_id="q7",
        )
    elif question_id == "q9":
        dependency_snapshot = _build_question_dependency_snapshot(
            snapshot_map or {},
            upto_question_id="q8",
        )
        context_updates["q1_q8_snapshot"] = dependency_snapshot
        context_updates["q1_q8"] = dependency_snapshot

    return {
        "tool_id": f"nine_questions.{question_id}",
        "summary": summary,
        "confidence": 0.0,
        "result": {
            "question_id": question_id,
            "error": "missing_snapshot",
            "reason": summary,
        },
        "context_updates": context_updates,
        "trace_id": f"{question_id}:no-trace",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cache_status": "缺失",
        "provider_name": None,
        "mounted_plugins": [],
    }


def _isolate_question_snapshot_payloads(
    question_id: str,
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    own_summary_key = QUESTION_TITLES.get(question_id)

    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False)) if payload else {}
        if not own_summary_key:
            return normalized

        summaries = normalized.get("nine_questions")
        if isinstance(summaries, dict):
            own_value = summaries.get(own_summary_key)
            normalized["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}

        nested_context_updates = normalized.get("context_updates")
        if isinstance(nested_context_updates, dict):
            nested_summaries = nested_context_updates.get("nine_questions")
            if isinstance(nested_summaries, dict):
                own_value = nested_summaries.get(own_summary_key)
                nested_context_updates["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}
        return normalized

    return _normalize(result_payload), _normalize(context_updates)


def _build_question_dependency_snapshot(
    snapshot_map: dict[str, dict[str, Any]],
    *,
    upto_question_id: str,
) -> dict[str, Any]:
    ordered_ids = [f"q{i}" for i in range(1, 10)]
    if upto_question_id not in ordered_ids:
        return {}

    result: dict[str, Any] = {}
    max_index = ordered_ids.index(upto_question_id)
    for question_id in ordered_ids[: max_index + 1]:
        snapshot = snapshot_map.get(question_id)
        if not isinstance(snapshot, dict):
            continue
        result_payload = snapshot.get("result")
        result_payload = result_payload if isinstance(result_payload, dict) else {}
        context_updates = snapshot.get("context_updates")
        context_updates = context_updates if isinstance(context_updates, dict) else {}

        if question_id == "q1":
            result[question_id] = (
                result_payload.get("workspace_domain_inference")
                or context_updates.get("workspace_domain_inference")
                or {}
            )
        elif question_id == "q2":
            result[question_id] = (
                result_payload.get("role_profile")
                or context_updates.get("q2_role_profile")
                or {}
            )
        elif question_id == "q3":
            result[question_id] = (
                result_payload.get("resource_evaluation")
                or context_updates.get("q3_resource_evaluation")
                or {}
            )
        elif question_id == "q4":
            result[question_id] = (
                result_payload.get("capability_boundary_profile")
                or context_updates.get("q4_capability_boundary_profile")
                or {}
            )
        elif question_id == "q5":
            result[question_id] = (
                result_payload.get("authorization_boundary_profile")
                or context_updates.get("q5_authorization_boundary_profile")
                or context_updates.get("q5_permission_boundary")
                or {}
            )
        elif question_id == "q6":
            result[question_id] = (
                result_payload.get("forbidden_zone_profile")
                or context_updates.get("q6_forbidden_zone_profile")
                or {}
            )
        elif question_id == "q7":
            result[question_id] = (
                result_payload.get("alternative_strategy_profile")
                or context_updates.get("q7_alternative_strategy_profile")
                or {}
            )
        elif question_id == "q8":
            result[question_id] = (
                result_payload.get("objective_profile")
                or context_updates.get("q8_objective_profile")
                or {}
            )

    summaries: dict[str, Any] = {}
    for question_id in ordered_ids[: max_index + 1]:
        snapshot = snapshot_map.get(question_id)
        if not isinstance(snapshot, dict):
            continue
        context_updates = snapshot.get("context_updates")
        context_updates = context_updates if isinstance(context_updates, dict) else {}
        summary_map = context_updates.get("nine_questions")
        if isinstance(summary_map, dict):
            summaries.update({str(k): v for k, v in summary_map.items() if str(k).strip()})
    if summaries:
        result["summaries"] = summaries

    return result


def _build_flat_dependency_context(
    snapshot_map: dict[str, dict[str, Any]],
    *,
    upto_question_id: str,
) -> dict[str, Any]:
    ordered_ids = [f"q{i}" for i in range(1, 10)]
    if upto_question_id not in ordered_ids:
        return {}

    result: dict[str, Any] = {}
    max_index = ordered_ids.index(upto_question_id)
    for question_id in ordered_ids[: max_index + 1]:
        snapshot = snapshot_map.get(question_id)
        if not isinstance(snapshot, dict):
            continue
        result_payload = snapshot.get("result")
        result_payload = result_payload if isinstance(result_payload, dict) else {}
        context_updates = snapshot.get("context_updates")
        context_updates = context_updates if isinstance(context_updates, dict) else {}

        if question_id == "q1":
            for key in (
                "workspace_domain_inference",
                "physical_host_state",
                "workspace_structure_analysis",
                "workspace_content_samples",
                "q1_scene_model",
                "q1_uncertainty_profile",
                "q1_sensory_audit",
                "q1_compression_snapshot",
                "q1_llm_upgrade",
            ):
                value = result_payload.get(key)
                if value in (None, {}, [], ""):
                    value = context_updates.get(key)
                if value not in (None, {}, [], ""):
                    result[key] = value
        elif question_id == "q2":
            for key in (
                "q2_role_profile",
                "q2_mission_boundary",
                "identity_kernel_snapshot",
                "manual_role_overrides",
                "risk_weight",
            ):
                value = context_updates.get(key)
                if value in (None, {}, [], ""):
                    alias_key = {
                        "q2_role_profile": "role_profile",
                        "q2_mission_boundary": "mission_boundary",
                    }.get(key)
                    value = result_payload.get(alias_key) if alias_key else None
                if value not in (None, {}, [], ""):
                    result[key] = value
        elif question_id == "q3":
            for key in (
                "q3_unified_asset_inventory",
                "q3_resource_evaluation",
                "q3_humanized_asset_inventory",
                "workspaces_and_permissions",
                "memory_and_strategy",
                "workspace_assets",
                "permissions",
                "loaded_memories",
            ):
                value = context_updates.get(key)
                if value in (None, {}, [], ""):
                    alias_key = {
                        "q3_unified_asset_inventory": "unified_asset_inventory",
                        "q3_resource_evaluation": "resource_evaluation",
                    }.get(key)
                    value = result_payload.get(alias_key) if alias_key else None
                if value not in (None, {}, [], ""):
                    result[key] = value
            unified_inventory = result.get("q3_unified_asset_inventory")
            if isinstance(unified_inventory, dict):
                connected_agents = unified_inventory.get("connected_agents")
                if isinstance(connected_agents, list) and connected_agents:
                    result.setdefault("q3_connected_agents", connected_agents)
        elif question_id == "q4":
            for key in (
                "q4_capability_boundary_profile",
                "q4_permission_profile",
                "q4_active_execution_domains",
                "q4_capability_baseline",
                "q4_capability_evidence",
                "q4_functional_capabilities",
            ):
                value = context_updates.get(key)
                if value in (None, {}, [], "") and key == "q4_capability_boundary_profile":
                    value = result_payload.get("capability_boundary_profile")
                if value not in (None, {}, [], ""):
                    result[key] = value
        elif question_id == "q5":
            for key in (
                "q5_authorization_boundary_profile",
                "q5_permission_boundary",
                "q5_authorization_baseline",
                "q5_agent_trust_status",
                "contact_policy",
                "tenant_scope",
            ):
                value = context_updates.get(key)
                if value in (None, {}, [], "") and key == "q5_authorization_boundary_profile":
                    value = result_payload.get("authorization_boundary_profile")
                if value not in (None, {}, [], ""):
                    result[key] = value
        elif question_id == "q6":
            for key in (
                "q6_forbidden_zone_profile",
                "q6_global_constraints",
                "q6_redline_hints",
                "q6_forbidden_zone_baseline",
            ):
                value = context_updates.get(key)
                if value in (None, {}, [], "") and key == "q6_forbidden_zone_profile":
                    value = result_payload.get("forbidden_zone_profile")
                if value not in (None, {}, [], ""):
                    result[key] = value
        elif question_id == "q7":
            for key in (
                "q7_alternative_strategy_profile",
                "q7_functional_alternatives",
                "q7_alternative_strategy_baseline",
                "q7_resource_bottlenecks",
                "q7_capability_limits",
                "q7_permission_boundaries",
                "q7_absolute_red_lines",
            ):
                value = context_updates.get(key)
                if value in (None, {}, [], "") and key == "q7_alternative_strategy_profile":
                    value = result_payload.get("alternative_strategy_profile")
                if value not in (None, {}, [], ""):
                    result[key] = value
        elif question_id == "q8":
            for key in (
                "q8_objective_profile",
                "q8_task_queue",
                "q8_priority_baseline",
                "q8_persistent_task_state",
                "q8_q1_q7_snapshot",
            ):
                value = context_updates.get(key)
                if value in (None, {}, [], ""):
                    alias_key = {
                        "q8_objective_profile": "objective_profile",
                        "q8_task_queue": "task_queue",
                    }.get(key)
                    value = result_payload.get(alias_key) if alias_key else None
                if value not in (None, {}, [], ""):
                    result[key] = value

    return result


def _merge_missing_context_fields(
    target: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    merged = json.loads(json.dumps(target, ensure_ascii=False)) if target else {}
    for key, value in source.items():
        current = merged.get(key)
        if current in (None, "", [], {}):
            merged[key] = value
    return merged


def _inject_direct_question_dependencies(
    question_id: str,
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
    snapshot_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged_result = json.loads(json.dumps(result_payload, ensure_ascii=False)) if result_payload else {}
    merged_context = json.loads(json.dumps(context_updates, ensure_ascii=False)) if context_updates else {}

    if question_id == "q2":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q1"),
        )
    elif question_id == "q3":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q2"),
        )
    elif question_id == "q4":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q3"),
        )
    elif question_id == "q5":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q4"),
        )
    elif question_id == "q6":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q5"),
        )
    elif question_id == "q7":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q6"),
        )
    elif question_id == "q8":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q7"),
        )
        dependency_snapshot = _build_question_dependency_snapshot(snapshot_map, upto_question_id="q7")
        if dependency_snapshot:
            merged_context["q1_q7_snapshot"] = dependency_snapshot
    elif question_id == "q9":
        merged_context = _merge_missing_context_fields(
            merged_context,
            _build_flat_dependency_context(snapshot_map, upto_question_id="q8"),
        )
        dependency_snapshot = _build_question_dependency_snapshot(snapshot_map, upto_question_id="q8")
        if dependency_snapshot:
            merged_context["q1_q8_snapshot"] = dependency_snapshot
            merged_context["q1_q8"] = dependency_snapshot

    return merged_result, merged_context


def _normalize_question_projection_payloads(
    question_id: str,
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_result = json.loads(json.dumps(result_payload, ensure_ascii=False)) if result_payload else {}
    normalized_context = json.loads(json.dumps(context_updates, ensure_ascii=False)) if context_updates else {}

    if question_id == "q3":
        unified_inventory = normalized_result.get("unified_asset_inventory")
        if isinstance(unified_inventory, dict) and "q3_unified_asset_inventory" not in normalized_context:
            normalized_context["q3_unified_asset_inventory"] = unified_inventory

        resource_evaluation = normalized_result.get("resource_evaluation")
        if isinstance(resource_evaluation, dict) and "q3_resource_evaluation" not in normalized_context:
            normalized_context["q3_resource_evaluation"] = resource_evaluation

    return normalized_result, normalized_context


def _state_has_question_data(state: Any) -> bool:
    snapshot_map = get_question_snapshot_map(state)
    return bool(snapshot_map)


def _merge_trace_projection_payloads(
    snapshot: dict[str, Any],
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
    trace_detail: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot_execution_context = snapshot.get("execution_context")
    snapshot_execution_context = snapshot_execution_context if isinstance(snapshot_execution_context, dict) else {}
    snapshot_execution_result = snapshot.get("execution_result")
    snapshot_execution_result = snapshot_execution_result if isinstance(snapshot_execution_result, dict) else {}

    trace_context = trace_detail.get("context") if isinstance(trace_detail, dict) else {}
    trace_context = trace_context if isinstance(trace_context, dict) else {}
    trace_result = trace_detail.get("result") if isinstance(trace_detail, dict) else {}
    trace_result = trace_result if isinstance(trace_result, dict) else {}

    nested_result_context_updates = result_payload.get("context_updates")
    nested_result_context_updates = (
        nested_result_context_updates if isinstance(nested_result_context_updates, dict) else {}
    )

    merged_result = dict(snapshot_execution_result)
    merged_result.update(trace_result)
    merged_result.update(result_payload)

    merged_context = dict(snapshot_execution_context)
    merged_context.update(trace_context)
    merged_context.update(nested_result_context_updates)
    merged_context.update(context_updates)

    # Hoist context_snapshot contents to top level so evidence functions can
    # access cross-question profiles (e.g. q4_capability_boundary_profile)
    # directly on context_payload without knowing the nesting.
    ctx_snap = merged_context.get("context_snapshot")
    if isinstance(ctx_snap, dict):
        for k, v in ctx_snap.items():
            merged_context.setdefault(k, v)  # don't overwrite plugin-specific outputs

    return merged_result, merged_context


def _state_has_complete_question_data(state: Any) -> bool:
    snapshot_map = get_question_snapshot_map(state)
    if not snapshot_map:
        return False

    snapshot_version = 0
    if isinstance(state, dict):
        snapshot_version = int(state.get("snapshot_version", 0) or 0)
    else:
        snapshot_version = int(getattr(state, "snapshot_version", 0) or 0)

    if snapshot_version >= len(EXPECTED_QUESTION_IDS):
        return True

    return all(question_id in snapshot_map for question_id in EXPECTED_QUESTION_IDS)


def _state_requires_refresh(state: Any) -> bool:
    if isinstance(state, dict):
        return bool(state.get("dirty_questions") or [])
    return bool(getattr(state, "dirty_questions", []) or [])


async def _persist_kernel_nine_question_state(
    request: Request,
    session_id: str,
    state: Any,
) -> None:
    """Mirror kernel nine-question results into the local SQLite state store."""
    snapshot_map = get_question_snapshot_map(state)
    if not snapshot_map:
        return

    state_mgr = get_nine_question_state_manager(request)
    try:
        await state_mgr.get_state(session_id)
    except ValueError:
        await state_mgr.bootstrap_state(session_id)

    if isinstance(state, dict):
        snapshot_version = int(state.get("snapshot_version", len(snapshot_map)))
        last_refresh_reason = state.get("last_refresh_reason")
    else:
        snapshot_version = int(getattr(state, "snapshot_version", len(snapshot_map)))
        last_refresh_reason = getattr(state, "last_refresh_reason", None)

    await state_mgr.update_state(
        session_id,
        question_snapshots=snapshot_map,
        snapshot_version=snapshot_version,
        last_refresh_reason=last_refresh_reason,
        dirty_questions=[],
    )


async def _ensure_kernel_backed_session(request: Request, session: Any) -> Any:
    """Align the web-console session with a real kernel session.

    Nine-question execution and reporting are backed by kernel session state.
    If the current web-console session does not exist in the kernel runtime,
    switch to an existing kernel session or create one and mirror it into the
    web-console session store.
    """
    facade = get_kernel_service_facade(request)
    session_mgr = get_session_manager(request)
    workspace = getattr(session, "workspace", None) or getattr(request.app.state, "default_workspace", "/workspace")

    session_id = getattr(session, "session_id", None)
    if session_id and facade.get_session_meta(session_id):
        request.app.state.session = session
        request.app.state.active_session = session
        return session

    kernel_session_id: str | None = None
    active_kernel_sessions = facade.list_active_sessions()
    if active_kernel_sessions:
        kernel_session_id = active_kernel_sessions[0]
    else:
        kernel_session_id = facade.create_kernel_session(user_id="web-console")

    try:
        resolved = await session_mgr.get_active_session(kernel_session_id)
    except ValueError:
        resolved = await session_mgr.create_session(workspace=workspace, session_id=kernel_session_id)

    request.app.state.session = resolved
    request.app.state.active_session = resolved
    return resolved


async def get_or_create_session(request: Request) -> Any:
    """Get the active session, or create one if none exists
    
    Returns:
        Session object with session_id, workspace, etc.
    """
    session_mgr = get_session_manager(request)
    
    if not session_mgr:
        raise HTTPException(status_code=503, detail="SessionManager not available")
    
    try:
        # Prefer an already attached session snapshot from app.state.
        session = getattr(request.app.state, "session", None) or getattr(request.app.state, "active_session", None)
        session_id = getattr(session, "session_id", None) if session is not None else None
        if session_id:
            try:
                resolved = await session_mgr.get_active_session(session_id)
                return await _ensure_kernel_backed_session(request, resolved)
            except ValueError:
                logger.info("Discarding stale web-console session %s for nine-question flow", session_id)

        # Fall back to the first active session if the manager already has one.
        active_sessions = await session_mgr.list_active_sessions()
        if active_sessions:
            resolved = active_sessions[0]
            return await _ensure_kernel_backed_session(request, resolved)
        
        # Create new session with default workspace
        workspace = getattr(request.app.state, "default_workspace", "/workspace")
        session = await session_mgr.create_session(workspace=workspace)
        return await _ensure_kernel_backed_session(request, session)
    except Exception as e:
        logger.error(f"Session management error: {e}")
        raise HTTPException(status_code=503, detail="Failed to manage session")


QUESTION_TITLES = {
    "q1": "我在哪",
    "q2": "我是谁",
    "q3": "我有什么",
    "q4": "我能做什么",
    "q5": "我被允许做什么",
    "q6": "我即使能做也不该做什么",
    "q7": "我还可以做什么",
    "q8": "我现在应该做什么",
    "q9": "我应该如何行动",
}


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _humanize_question_summary(
    question_id: str,
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> str:
    if question_id == "q1":
        workspace_domain = (
            result_payload.get("workspace_domain_inference")
            or context_updates.get("workspace_domain_inference")
            or {}
        )
        workspace_domain = workspace_domain if isinstance(workspace_domain, dict) else {}
        primary_domain = str(workspace_domain.get("primary_domain") or "").strip()
        confidence = workspace_domain.get("confidence")
        secondary_count = len(_coerce_string_list(workspace_domain.get("secondary_domains")))
        uncertainty_count = len(_coerce_string_list(workspace_domain.get("uncertainties")))
        parts = []
        if primary_domain:
            parts.append(f"当前工作区主领域判断为 {primary_domain}")
        if isinstance(confidence, (int, float)):
            parts.append(f"置信度 {float(confidence):.2f}")
        if secondary_count:
            parts.append(f"次领域 {secondary_count} 项")
        if uncertainty_count:
            parts.append(f"不确定因素 {uncertainty_count} 项")
        return "，".join(parts)

    if question_id == "q2":
        role_profile = (
            result_payload.get("role_profile")
            or context_updates.get("q2_role_profile")
            or {}
        )
        role_profile = role_profile if isinstance(role_profile, dict) else {}
        mission_boundary = (
            result_payload.get("mission_boundary")
            or context_updates.get("q2_mission_boundary")
            or {}
        )
        mission_boundary = mission_boundary if isinstance(mission_boundary, dict) else {}
        identity_role = str(role_profile.get("identity_role") or "").strip()
        active_role = str(role_profile.get("active_role") or "").strip()
        current_mission = str(mission_boundary.get("current_mission") or "").strip()
        parts = []
        if identity_role:
            parts.append(f"当前身份角色为 {identity_role}")
        if active_role:
            parts.append(f"活跃角色为 {active_role}")
        if current_mission:
            parts.append(f"当前使命：{current_mission}")
        return "，".join(parts)

    if question_id == "q3":
        resource_eval = (
            result_payload.get("resource_evaluation")
            or result_payload.get("sufficiency_assessment")
            or context_updates.get("q3_resource_evaluation")
            or {}
        )
        resource_eval = resource_eval if isinstance(resource_eval, dict) else {}
        resource_status = str(
            resource_eval.get("resource_status_label")
            or resource_eval.get("resource_status")
            or ""
        ).strip()
        missing_assets = _coerce_string_list(resource_eval.get("missing_critical_assets"))
        bottleneck = str(resource_eval.get("bottleneck_node") or "").strip()
        parts = []
        if resource_status:
            parts.append(f"当前资源状态：{resource_status}")
        if missing_assets:
            parts.append(f"缺失关键资产 {len(missing_assets)} 项")
        if bottleneck:
            parts.append(f"主要瓶颈：{bottleneck}")
        return "，".join(parts)

    if question_id == "q4":
        capability_profile = (
            result_payload.get("capability_boundary_profile")
            or context_updates.get("q4_capability_boundary_profile")
            or {}
        )
        capability_profile = capability_profile if isinstance(capability_profile, dict) else {}
        upper_limits = _coerce_string_list(capability_profile.get("capability_upper_limits"))
        actionable_space = _coerce_string_list(capability_profile.get("actionable_space"))
        executable_strategies = _coerce_string_list(capability_profile.get("executable_strategies"))
        parts = []
        if upper_limits:
            parts.append(f"能力上限 {len(upper_limits)} 项")
        if actionable_space:
            parts.append(f"可行动空间 {len(actionable_space)} 项")
        if executable_strategies:
            parts.append(f"可执行策略 {len(executable_strategies)} 项")
        return "，".join(parts)

    if question_id == "q5":
        auth_profile = (
            result_payload.get("authorization_boundary_profile")
            or context_updates.get("q5_authorization_boundary_profile")
            or context_updates.get("q5_permission_boundary")
            or {}
        )
        auth_profile = auth_profile if isinstance(auth_profile, dict) else {}
        execution_tier = str(auth_profile.get("execution_tier") or "").strip()
        allowed_actions = _coerce_string_list(auth_profile.get("allowed_action_space"))
        forbidden_actions = _coerce_string_list(auth_profile.get("forbidden_action_space"))
        escalation_actions = _coerce_string_list(auth_profile.get("requires_escalation_actions"))
        parts = []
        if execution_tier:
            parts.append(f"执行层级：{execution_tier}")
        if allowed_actions:
            parts.append(f"允许动作 {len(allowed_actions)} 项")
        if forbidden_actions:
            parts.append(f"禁止动作 {len(forbidden_actions)} 项")
        if escalation_actions:
            parts.append(f"需升级确认 {len(escalation_actions)} 项")
        return "，".join(parts)

    if question_id == "q6":
        forbidden_profile = (
            result_payload.get("forbidden_zone_profile")
            or context_updates.get("q6_forbidden_zone_profile")
            or {}
        )
        forbidden_profile = forbidden_profile if isinstance(forbidden_profile, dict) else {}
        red_lines = _coerce_string_list(forbidden_profile.get("absolute_red_lines"))
        bans = _coerce_string_list(forbidden_profile.get("performance_tradeoff_bans"))
        prohibited = _coerce_string_list(forbidden_profile.get("prohibited_strategies"))
        contamination = _coerce_string_list(forbidden_profile.get("contamination_risks"))
        parts = []
        if red_lines:
            parts.append(f"绝对红线 {len(red_lines)} 项")
        if bans:
            parts.append(f"性能权衡禁令 {len(bans)} 项")
        if prohibited:
            parts.append(f"禁止策略 {len(prohibited)} 项")
        if contamination:
            parts.append(f"污染风险 {len(contamination)} 项")
        return "，".join(parts)

    if question_id == "q7":
        strategy_profile = (
            result_payload.get("alternative_strategy_profile")
            or context_updates.get("q7_alternative_strategy_profile")
            or {}
        )
        strategy_profile = strategy_profile if isinstance(strategy_profile, dict) else {}
        fallback_plans = _coerce_string_list(strategy_profile.get("fallback_plans"))
        degradation = _coerce_string_list(strategy_profile.get("degradation_strategies"))
        collaboration = _coerce_string_list(strategy_profile.get("collaboration_switches"))
        exploratory = _coerce_string_list(strategy_profile.get("exploratory_actions"))
        parts = []
        if fallback_plans:
            parts.append(f"回退方案 {len(fallback_plans)} 项")
        if degradation:
            parts.append(f"降级策略 {len(degradation)} 项")
        if collaboration:
            parts.append(f"协作切换 {len(collaboration)} 项")
        if exploratory:
            parts.append(f"探索动作 {len(exploratory)} 项")
        return "，".join(parts)

    if question_id == "q8":
        objective_profile = (
            result_payload.get("objective_profile")
            or context_updates.get("q8_objective_profile")
            or {}
        )
        objective_profile = objective_profile if isinstance(objective_profile, dict) else {}
        task_queue = (
            result_payload.get("task_queue")
            or context_updates.get("q8_task_queue")
            or {}
        )
        task_queue = task_queue if isinstance(task_queue, dict) else {}
        objective = str(
            objective_profile.get("current_mission")
            or objective_profile.get("current_primary_objective")
            or ""
        ).strip()
        next_count = len(task_queue.get("next_self_tasks") or []) if isinstance(task_queue.get("next_self_tasks"), list) else len(_coerce_string_list(task_queue.get("next_self_tasks")))
        blocked_count = len(task_queue.get("blocked_self_tasks") or []) if isinstance(task_queue.get("blocked_self_tasks"), list) else len(_coerce_string_list(task_queue.get("blocked_self_tasks")))
        proactive_count = len(task_queue.get("proactive_actions") or []) if isinstance(task_queue.get("proactive_actions"), list) else len(_coerce_string_list(task_queue.get("proactive_actions")))
        parts = []
        if objective:
            parts.append(f"当前主目标：{objective}")
        parts.append(f"下一步 {next_count} 项")
        parts.append(f"阻塞任务 {blocked_count} 项")
        parts.append(f"主动行动 {proactive_count} 项")
        return "，".join(parts)

    if question_id == "q9":
        evaluation_profile = (
            result_payload.get("evaluation_profile")
            or context_updates.get("q9_evaluation_profile")
            or {}
        )
        evaluation_profile = evaluation_profile if isinstance(evaluation_profile, dict) else {}
        evolution_profile = (
            result_payload.get("evolution_profile")
            or context_updates.get("q9_evolution_profile")
            or {}
        )
        evolution_profile = evolution_profile if isinstance(evolution_profile, dict) else {}
        escalation_profile = (
            result_payload.get("escalation_profile")
            or context_updates.get("q9_escalation_profile")
            or {}
        )
        escalation_profile = escalation_profile if isinstance(escalation_profile, dict) else {}
        style = str(evaluation_profile.get("evaluation_style") or "").strip()
        risk = str(
            evaluation_profile.get("risk_level")
            or evaluation_profile.get("risk_tolerance")
            or ""
        ).strip()
        conservative = evaluation_profile.get("conservative_mode_triggered")
        allowed_count = len(_coerce_string_list(evolution_profile.get("allowed_directions")))
        confirm_count = len(_coerce_string_list(escalation_profile.get("confirmation_required_conditions")))
        parts = []
        if style:
            parts.append(f"行动评估风格：{style}")
        if risk:
            parts.append(f"风险容忍度：{risk}")
        if conservative is True:
            parts.append("当前处于保守模式")
        parts.append(f"允许方向 {allowed_count} 项")
        parts.append(f"确认条件 {confirm_count} 项")
        return "，".join(parts)

    return ""


def _derive_provider_name(
    snapshot: dict[str, Any],
    trace_detail: dict[str, Any] | None,
) -> str | None:
    provider_name = str(snapshot.get("provider_name") or "").strip()
    if provider_name:
        return provider_name

    llm_trace_payload = snapshot.get("llm_trace_payload")
    llm_trace_payload = llm_trace_payload if isinstance(llm_trace_payload, dict) else {}
    provider_name = str(llm_trace_payload.get("provider_name") or "").strip()
    if provider_name:
        return provider_name

    if isinstance(trace_detail, dict):
        trace_payload = trace_detail.get("llm_trace_payload")
        trace_payload = trace_payload if isinstance(trace_payload, dict) else {}
        provider_name = str(
            trace_payload.get("provider_name")
            or trace_detail.get("provider_name")
            or ""
        ).strip()
        if provider_name:
            return provider_name

    return None


def _derive_cache_status(
    snapshot: dict[str, Any],
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> str:
    cache_status = str(snapshot.get("cache_status") or "").strip()
    if cache_status and cache_status != "未知":
        return cache_status

    trace_id = str(snapshot.get("trace_id") or "").strip()
    if not result_payload and not context_updates and (not trace_id or trace_id.endswith(":no-trace")):
        return "缺失"

    if result_payload or context_updates:
        return "已就绪"

    if trace_id and not trace_id.endswith(":no-trace"):
        return "已缓存"

    return "未知"


def _derive_question_summary(
    question_id: str,
    snapshot: dict[str, Any],
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
) -> str:
    humanized = _humanize_question_summary(question_id, result_payload, context_updates)
    if humanized:
        return humanized

    summary_key = QUESTION_TITLES.get(question_id)
    summary_map = context_updates.get("nine_questions")
    if isinstance(summary_map, dict):
        text = str(summary_map.get(summary_key) or "").strip()
        if text:
            return text

    summary = str(snapshot.get("summary") or "").strip()
    if summary:
        return summary

    return ""


async def get_nine_question_state(request: Request, session_id: str) -> Any:
    """Get nine-question state for a session
    
    Returns:
        NineQuestionState object with question snapshots, dirty questions, etc.
    """
    facade = get_kernel_service_facade(request)
    state_mgr = get_nine_question_state_manager(request)

    try:
        persisted_state = await state_mgr.get_state(session_id)
    except ValueError:
        persisted_state = None

    if (
        persisted_state is not None
        and _state_has_complete_question_data(persisted_state)
        and not _state_requires_refresh(persisted_state)
    ):
        return persisted_state

    full_state = facade.get_nine_question_state(session_id)
    if _state_has_complete_question_data(full_state):
        await _persist_kernel_nine_question_state(request, session_id, full_state)
        return full_state

    try:
        facade.ensure_nine_questions_bootstrap(session_id)
    except ValueError:
        logger.warning("Kernel nine-question bootstrap skipped for unknown session %s", session_id)
    except Exception as exc:
        logger.warning("Kernel nine-question bootstrap failed for %s: %s", session_id, exc)

    full_state = facade.get_nine_question_state(session_id)
    if _state_has_complete_question_data(full_state):
        await _persist_kernel_nine_question_state(request, session_id, full_state)
        return full_state
    
    if not state_mgr:
        raise HTTPException(status_code=503, detail="StateManager not available")
    
    try:
        try:
            state = await state_mgr.get_state(session_id)
        except ValueError:
            state = await state_mgr.bootstrap_state(session_id)
        if not state:
            state = await state_mgr.bootstrap_state(session_id)
        return state
    except Exception as e:
        logger.error(f"State management error: {e}")
        raise HTTPException(status_code=503, detail="Failed to manage state")


def get_question_snapshot_map(state: Any) -> dict[str, dict[str, Any]]:
    if isinstance(state, dict):
        snapshots = state.get("question_snapshots")
        if isinstance(snapshots, dict):
            return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
        responses = state.get("responses")
        if isinstance(responses, dict):
            normalized: dict[str, dict[str, Any]] = {}
            state_timestamp = str(state.get("last_updated_at") or datetime.now(timezone.utc).isoformat())
            for question_id, response in responses.items():
                if not isinstance(response, dict):
                    continue
                normalized[str(question_id)] = {
                    "tool_id": f"nine_questions.{question_id}",
                    "summary": str(response.get("answer") or ""),
                    "confidence": float(response.get("confidence") or 0.0),
                    "result": response,
                    "context_updates": {},
                    "trace_id": str(response.get("trace_id") or f"{question_id}:no-trace"),
                    "timestamp": str(response.get("timestamp") or state_timestamp),
                }
            return normalized
        return {}

    snapshots = getattr(state, "question_snapshots", None)
    if isinstance(snapshots, dict):
        return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
    return {}


async def build_question_report_items(
    request: Request,
    state: Any,
    include_trace_detail: bool = False,
    question_filter: Optional[str] = None,
) -> list[NineQuestionReportItem]:
    """Build report items for nine questions
    
    Args:
        request: FastAPI request
        state: Current nine-question state
        include_trace_detail: Whether to include full trace details (expensive)
        question_filter: If specified, only return this question (e.g., 'q1')
    
    Returns:
        List of NineQuestionReportItem for each question
    """
    from .trace_builder import build_trace_detail
    
    items = []
    snapshot_map = get_question_snapshot_map(state)
    updated_snapshot_map = dict(snapshot_map)
    snapshots_changed = False
    question_ids = [question_filter] if question_filter else [f"q{i}" for i in range(1, 10)]
    
    for question_id in question_ids:
        snapshot = snapshot_map.get(question_id)
        original_snapshot = snapshot if isinstance(snapshot, dict) else None
        if not snapshot or not isinstance(snapshot, dict):
            snapshot = _build_missing_snapshot(question_id, snapshot_map)
        trace_id = snapshot.get("trace_id")
        trace_detail = None
        
        if include_trace_detail and trace_id:
            try:
                session = await get_or_create_session(request)
                trace_detail = await build_trace_detail(
                    request=request,
                    trace_id=trace_id,
                    session_id=session.session_id,
                )
            except Exception as e:
                logger.warning(f"Failed to build trace detail for {trace_id}: {e}")
        
        context_updates = snapshot.get("context_updates", {}) or {}
        result_payload = snapshot.get("result", {}) or {}
        context_updates = context_updates if isinstance(context_updates, dict) else {}
        result_payload = result_payload if isinstance(result_payload, dict) else {}
        result_payload, context_updates = _merge_trace_projection_payloads(
            snapshot,
            result_payload,
            context_updates,
            trace_detail if isinstance(trace_detail, dict) else None,
        )
        result_payload, context_updates = _isolate_question_snapshot_payloads(
            question_id,
            result_payload,
            context_updates,
        )
        result_payload, context_updates = _normalize_question_projection_payloads(
            question_id,
            result_payload,
            context_updates,
        )
        result_payload, context_updates = _inject_direct_question_dependencies(
            question_id,
            result_payload,
            context_updates,
            updated_snapshot_map,
        )
        handler = QUESTION_HANDLERS[question_id]
        preprocessed_evidence = handler["evidence"](context_updates)
        inference_result = handler["result"](result_payload)
        if inference_result is None and isinstance(context_updates, dict):
            inference_result = handler["result"](context_updates)

        # --- Error / unavailable propagation ---------------------------------
        # 1. Plugin execution error already recorded in snapshot.
        execution_error = snapshot.get("error") or snapshot.get("execution_error")
        if execution_error:
            logger.error(
                "Nine-question %s execution error for session (trace=%s): %s",
                question_id,
                snapshot.get("trace_id", "unknown"),
                execution_error,
            )
            context_updates = dict(context_updates)
            context_updates.setdefault("_execution_error", str(execution_error))
            context_updates.setdefault("_execution_error_hint", f"{QUESTION_TITLES.get(question_id, question_id)} 执行失败：{execution_error}")

        # 2. Evidence is None → upstream data / service unavailable.
        if preprocessed_evidence is None and snapshot.get("snapshot_status") != "missing":
            logger.error(
                "Nine-question %s preprocessed_evidence is None (service unavailable or upstream data missing). "
                "trace_id=%s confidence=%.2f",
                question_id,
                snapshot.get("trace_id", "unknown"),
                float(snapshot.get("confidence") or 0.0),
            )
            context_updates = dict(context_updates)
            context_updates.setdefault(
                "_evidence_unavailable",
                f"{QUESTION_TITLES.get(question_id, question_id)} 证据不可用：上游服务未响应或数据缺失，请检查插件与服务连接状态。",
            )

        derived_summary = _derive_question_summary(
            question_id,
            snapshot,
            result_payload,
            context_updates,
        )

        item = NineQuestionReportItem(
            question_id=question_id,
            title=QUESTION_TITLES.get(question_id, question_id),
            tool_id=str(snapshot.get("tool_id") or f"nine_questions.{question_id}"),
            summary=derived_summary,
            confidence=float(snapshot.get("confidence") or 0.0),
            result=result_payload,
            context_updates=context_updates,
            trace_id=str(trace_id or f"{question_id}:no-trace"),
            timestamp=str(snapshot.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            preprocessed_evidence=preprocessed_evidence,
            inference_result=inference_result,
            q1_llm_upgrade=_extract_q1_llm_upgrade(context_updates) if question_id == "q1" else None,
            cache_status=_derive_cache_status(snapshot, result_payload, context_updates),
            provider_name=_derive_provider_name(
                snapshot,
                trace_detail if isinstance(trace_detail, dict) else None,
            ),
            llm_trace_payload=snapshot.get("llm_trace_payload") or (
                trace_detail.get("llm_trace_payload")
                if isinstance(trace_detail, dict)
                else None
            ),
        )
        items.append(item)

        if original_snapshot is not None:
            enriched_snapshot = dict(original_snapshot)
            enriched_snapshot["summary"] = derived_summary
            enriched_snapshot["result"] = result_payload
            enriched_snapshot["context_updates"] = context_updates
            if item.llm_trace_payload is not None:
                enriched_snapshot["llm_trace_payload"] = item.llm_trace_payload.model_dump(mode="json")
            execution_context = snapshot.get("execution_context")
            execution_context = execution_context if isinstance(execution_context, dict) else {}
            execution_result = snapshot.get("execution_result")
            execution_result = execution_result if isinstance(execution_result, dict) else {}
            if isinstance(trace_detail, dict):
                trace_context = trace_detail.get("context")
                if isinstance(trace_context, dict) and trace_context:
                    execution_context = trace_context
                trace_result = trace_detail.get("result")
                if isinstance(trace_result, dict) and trace_result:
                    execution_result = trace_result
            if execution_context:
                enriched_snapshot["execution_context"] = execution_context
            if execution_result:
                enriched_snapshot["execution_result"] = execution_result
            if enriched_snapshot != original_snapshot:
                updated_snapshot_map[question_id] = enriched_snapshot
                snapshots_changed = True

    if snapshots_changed:
        try:
            session = await get_or_create_session(request)
            state_mgr = get_nine_question_state_manager(request)
            try:
                await state_mgr.get_state(session.session_id)
            except ValueError:
                await state_mgr.bootstrap_state(session.session_id)
            snapshot_version = int(
                state.get("snapshot_version", len(updated_snapshot_map))
                if isinstance(state, dict)
                else getattr(state, "snapshot_version", len(updated_snapshot_map))
            )
            last_refresh_reason = (
                state.get("last_refresh_reason")
                if isinstance(state, dict)
                else getattr(state, "last_refresh_reason", None)
            )
            await state_mgr.update_state(
                session.session_id,
                question_snapshots=updated_snapshot_map,
                snapshot_version=max(snapshot_version, len(updated_snapshot_map)),
                last_refresh_reason=last_refresh_reason,
                dirty_questions=[],
            )
        except Exception as exc:
            logger.debug("Skipping nine-question snapshot backfill persistence: %s", exc)
    
    return items


def build_trace_id_map(state: Any, items: list[NineQuestionReportItem]) -> dict[str, str]:
    """Build a trace-id map that reflects any snapshot enrichment applied during item projection."""
    raw_trace_ids = {
        qid: str(item.get("trace_id") or "")
        for qid, item in get_question_snapshot_map(state).items()
    }
    for item in items:
        raw_trace_ids[item.question_id] = item.trace_id
    return raw_trace_ids


def validate_question_id(question_id: str) -> bool:
    """Validate if question_id is in valid format (q1-q9)"""
    return question_id in [f"q{i}" for i in range(1, 10)]
