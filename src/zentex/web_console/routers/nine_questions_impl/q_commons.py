from __future__ import annotations
"""Common Nine-Questions Service Layer

Provides shared utilities for:
- Session management (get/create)
- State management (get/update)
- Question report building
- Common error handling
"""


import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

from zentex.web_console.contracts.nine_questions import NineQuestionReportItem
from zentex.nine_questions.question_driver_framework import (
    ensure_mounted_plugins,
    ensure_question_driver_trace,
)
from .q_state import (
    _get_nine_question_service,
    get_or_create_session,
    get_question_snapshot_map,
)
from .route_handlers_shared import QUESTION_TITLES
from .evidence_q1 import _extract_q1_llm_upgrade
from .q_handlers import QUESTION_HANDLERS

logger = logging.getLogger(__name__)

EXPECTED_QUESTION_IDS = tuple(f"q{i}" for i in range(1, 10))


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        return value.model_dump(mode="json")
    return dict(value) if isinstance(value, dict) else {}


def _q8_task_to_web_binding(task: Any, outcome: dict[str, Any] | None) -> dict[str, Any]:
    contract = getattr(task, "contract", None)
    contract_payload = _model_dump(contract)
    verification = contract_payload.get("verification") if isinstance(contract_payload.get("verification"), dict) else {}
    metadata = getattr(task, "metadata", None)
    metadata = metadata if isinstance(metadata, dict) else {}
    status = getattr(task, "status", "")
    priority = getattr(task, "priority", "")
    return {
        "task_binding_status": "bound",
        "physical_task_id": str(getattr(task, "task_id", "") or ""),
        "task_status": str(getattr(status, "value", status) or ""),
        "task_priority": str(getattr(priority, "value", priority) or ""),
        "trace_id": str(metadata.get("trace_id") or ""),
        "queue_name": str(metadata.get("queue_name") or ""),
        "expected_outcome": contract_payload.get("expected_outcome") or metadata.get("expected_outcome") or {},
        "success_criteria": contract_payload.get("success_criteria") or metadata.get("success_criteria") or [],
        "acceptance_conditions": contract_payload.get("acceptance_conditions") or metadata.get("acceptance_conditions") or [],
        "verification_method": contract_payload.get("verification_method") or metadata.get("verification_method") or "",
        "risk_assessment": contract_payload.get("risk_assessment") or metadata.get("risk_assessment") or {},
        "verification_enabled": bool(verification.get("enabled")),
        "verification_strategy": str(verification.get("strategy") or ""),
        "task_outcome": outcome or None,
    }


def _enrich_q8_queue_rows_with_task_bindings(
    request: Request,
    *,
    trace_id: str,
    inference_result: Any,
) -> Any:
    if not inference_result:
        return inference_result
    app_state = getattr(getattr(request, "app", None), "state", None)
    task_service = getattr(app_state, "task_service", None)
    if task_service is None:
        return inference_result

    list_tasks = getattr(task_service, "list_tasks", None)
    if not callable(list_tasks):
        raise RuntimeError("Task service does not expose list_tasks() for Q8 binding")

    q8_tasks = list(list_tasks(metadata_filters={"source": "nine_questions.q8"}) or [])
    if trace_id and not trace_id.endswith(":no-trace"):
        q8_tasks = [
            task
            for task in q8_tasks
            if isinstance(getattr(task, "metadata", None), dict)
            and str(task.metadata.get("trace_id") or "") == trace_id
        ]

    by_queue_title: dict[tuple[str, str], Any] = {}
    for task in q8_tasks:
        metadata = getattr(task, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        key = (str(metadata.get("queue_name") or ""), str(getattr(task, "title", "") or "").strip())
        if key[0] and key[1] and key not in by_queue_title:
            by_queue_title[key] = task

    payload = _model_dump(inference_result)
    queue = payload.get("task_queue") if isinstance(payload.get("task_queue"), dict) else {}

    def _enrich_rows(queue_key: str, status: str) -> list[dict[str, Any]]:
        rows = queue.get(queue_key)
        if not isinstance(rows, list):
            return []
        enriched: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row) if isinstance(row, dict) else {"title": str(row or ""), "status": status}
            title = str(item.get("title") or "").strip()
            task = by_queue_title.get((queue_key, title))
            if task is None:
                enriched.append({**item, "task_binding_status": "missing"})
                continue
            outcome = task_service.get_task_outcome(task.task_id) if callable(getattr(task_service, "get_task_outcome", None)) else None
            enriched.append({**item, **_q8_task_to_web_binding(task, outcome)})
        return enriched

    queue["next_self_tasks"] = _enrich_rows("next_self_tasks", "next")
    queue["blocked_self_tasks"] = _enrich_rows("blocked_self_tasks", "blocked")
    queue["proactive_actions"] = _enrich_rows("proactive_actions", "proactive")
    payload["task_queue"] = queue
    return payload


def _state_has_question_data(state: Any) -> bool:
    snapshot_map = get_question_snapshot_map(state)
    return bool(snapshot_map)


def _merge_trace_projection_payloads(
    snapshot: dict[str, Any],
    result_payload: dict[str, Any],
    context_updates: dict[str, Any],
    trace_detail: dict[str, Optional[Any]],
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

    return merged_result, merged_context


def _state_has_complete_question_data(state: Any) -> bool:
    from .q_state import _state_has_complete_question_data as _shared_state_complete
    return _shared_state_complete(state)


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _material_trace_payload(
    *,
    question_id: str,
    snapshot: dict[str, Any],
    trace_detail: dict[str, Optional[Any]] | None,
    context_updates: dict[str, Any],
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    payload = snapshot.get("llm_trace_payload")
    if not isinstance(payload, dict) and trace_detail is not None:
        candidate = trace_detail.get("llm_trace_payload")
        payload = candidate if isinstance(candidate, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return ensure_question_driver_trace(
        question_id,
        payload,
        context_data=context_updates,
        raw_response=result_payload,
    )


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
    trace_detail: dict[str, Optional[Any]],
) -> Optional[str]:
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


async def build_question_report_items(
    request: Request,
    state: Any,
    include_trace_detail: bool = False,
    question_filter: Optional[str] = None,
) -> list[NineQuestionReportItem]:
    """Build report items for nine questions.

    Reads each question's fully-composed record directly from
    NineQuestionService.get_question_record() (upstream SQLite + filesystem),
    eliminating the old snapshot/context re-projection layer.  The snapshot is
    still fetched for lightweight metadata (trace_id, confidence, timestamp,
    provider_name) that is not part of the composed record.

    Args:
        request: FastAPI request
        state: Current nine-question state (used only for question_filter
               fallback; field reads are now upstream-sourced)
        include_trace_detail: Whether to fetch full trace details (slow path)
        question_filter: If set, only return this single question (e.g. 'q1')

    Returns:
        List of NineQuestionReportItem for each requested question
    """
    from .trace_builder import build_trace_detail

    nq_service = _get_nine_question_service(request)
    question_ids = [question_filter] if question_filter else [f"q{i}" for i in range(1, 10)]
    items = []

    for question_id in question_ids:
        # ── 1. Full composed record from upstream (SQLite → filesystem) ──────
        try:
            record = await nq_service.get_question_record(question_id)
        except Exception:
            logger.warning(
                "build_question_report_items: get_question_record failed for %s",
                question_id,
                exc_info=True,
            )
            record = {}

        composed = record.get("composed") if isinstance(record.get("composed"), dict) else {}
        raw_payload = composed.get("raw") if isinstance(composed.get("raw"), dict) else {}
        result_payload: dict[str, Any] = raw_payload.get("result") or {}
        context_updates: dict[str, Any] = raw_payload.get("context_updates") or {}
        preprocessed_evidence: dict[str, Any] = composed.get("evidence") or {}
        inference_result: Any = composed.get("inference") or {}

        # ── 2. Lightweight snapshot metadata (trace_id / confidence / ts) ────
        try:
            snapshot: dict[str, Any] = await nq_service.get_question_snapshot(question_id) or {}
        except Exception:
            logger.warning(
                "build_question_report_items: get_question_snapshot failed for %s",
                question_id,
                exc_info=True,
            )
            snapshot = {}

        trace_id = str(snapshot.get("trace_id") or f"{question_id}:no-trace")

        # ── 3. Optional trace detail (expensive; only on real trace_id) ───────
        trace_detail: dict[str, Optional[Any]] = None
        if include_trace_detail and trace_id and not trace_id.endswith(":no-trace"):
            try:
                session = await get_or_create_session(request)
                raw_td = await build_trace_detail(
                    request=request,
                    trace_id=trace_id,
                    session_id=session.session_id,
                )
                trace_detail = raw_td if isinstance(raw_td, dict) else None
            except Exception:
                logger.warning(
                    "build_question_report_items: build_trace_detail failed for trace %s",
                    trace_id,
                    exc_info=True,
                )

        # Merge trace detail payloads when present (fills gaps in record)
        if trace_detail is not None:
            result_payload, context_updates = _merge_trace_projection_payloads(
                snapshot,
                result_payload,
                context_updates,
                trace_detail,
            )

        # ── 4. Handler fallback for evidence / inference ──────────────────────
        handler = QUESTION_HANDLERS[question_id]
        if not preprocessed_evidence:
            preprocessed_evidence = handler["evidence"](context_updates)
        if not inference_result:
            inference_result = handler["result"](result_payload)
            if inference_result is None and isinstance(context_updates, dict):
                inference_result = handler["result"](context_updates)
        if question_id == "q8":
            inference_result = _enrich_q8_queue_rows_with_task_bindings(
                request,
                trace_id=trace_id,
                inference_result=inference_result,
            )

        derived_summary = _derive_question_summary(
            question_id,
            snapshot,
            result_payload,
            context_updates,
        )

        items.append(NineQuestionReportItem(
            question_id=question_id,
            title=QUESTION_TITLES.get(question_id, question_id),
            tool_id=str(snapshot.get("tool_id") or f"nine_questions.{question_id}"),
            summary=derived_summary,
            confidence=float(snapshot.get("confidence") or 0.0),
            result=result_payload,
            context_updates=context_updates,
            trace_id=trace_id,
            timestamp=str(snapshot.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            preprocessed_evidence=preprocessed_evidence,
            inference_result=inference_result,
            q1_llm_upgrade=_extract_q1_llm_upgrade(context_updates) if question_id == "q1" else None,
            cache_status=_derive_cache_status(snapshot, result_payload, context_updates),
            provider_name=_derive_provider_name(snapshot, trace_detail),
            mounted_plugins=ensure_mounted_plugins(
                question_id,
                snapshot.get("mounted_plugins") if isinstance(snapshot.get("mounted_plugins"), list) else [],
            ),
            llm_trace_payload=_material_trace_payload(
                question_id=question_id,
                snapshot=snapshot,
                trace_detail=trace_detail,
                context_updates=context_updates,
                result_payload=result_payload,
            ),
        ))

    return items
