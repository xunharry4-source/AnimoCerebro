"""Nine Questions API Route Handler v2 - Refactored with Facade-First Design

⚠️  MODULARIZATION CONSTRAINT - MAX 800 LINES
════════════════════════════════════════════════════════════════════
This module MUST NOT exceed 800 lines. All business logic extracted to:
  - q_commons.py: Shared nine-question logic
  - trace_builder.py: Trace construction & formatting
  - q1, q2, ..., q9 services in handlers/ subdirectory

This file contains ONLY route definitions that delegate to services.
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from zentex.tasks.models import TaskPriority, TaskStatus, TaskType, ZentexTask

from zentex.web_console.dependencies import (
    get_kernel_service_facade,
    get_session_manager,
    get_nine_question_state_manager,
    get_event_bus,
)
from zentex.web_console.contracts.nine_questions import (
    NineQuestionsRunRequest,
    NineQuestionsRunResponse,
    NineQuestionsReportPayload,
    NineQuestionReportItem,
)

# Import service layer
from .q_commons import (
    get_or_create_session,
    get_nine_question_state,
    build_question_report_items,
    build_trace_id_map,
    get_question_snapshot_map,
    _persist_kernel_nine_question_state,
)
from .trace_builder import build_trace_detail

router = APIRouter()
logger = logging.getLogger(__name__)


# ========== Constants ==========

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


def _stringify_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalize_q8_task_rows(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("task") or item.get("task_id") or item.get("id") or "").strip()
            if not title:
                continue
            normalized.append(
                {
                    "task_id": str(item.get("task_id") or item.get("id") or f"q8-task-{index}"),
                    "title": title,
                    "reason": str(item.get("reason") or "").strip(),
                    "priority": item.get("priority"),
                }
            )
        else:
            title = str(item or "").strip()
            if title:
                normalized.append(
                    {
                        "task_id": f"q8-task-{index}",
                        "title": title,
                        "reason": "",
                        "priority": None,
                    }
                )
    return normalized


def _stable_task_suffix(task: dict[str, Any], index: int) -> str:
    base = str(task.get("task_id") or task.get("title") or index).strip().lower()
    cleaned = "".join(char if char.isalnum() else "-" for char in base)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:64] or f"task-{index}"


def _coerce_task_priority(value: object, default_priority: TaskPriority) -> TaskPriority:
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
        }
        return mapping.get(normalized, default_priority)
    if isinstance(value, int):
        if value >= 90:
            return TaskPriority.CRITICAL
        if value >= 70:
            return TaskPriority.HIGH
        if value >= 40:
            return TaskPriority.MEDIUM
        return TaskPriority.LOW
    return default_priority


def _sync_task_record_fields(
    task_service: Any,
    task: ZentexTask,
    *,
    title: str,
    remarks: str,
    priority: TaskPriority,
    tags: list[str],
    metadata: dict[str, Any],
) -> None:
    task.title = title
    task.remarks = remarks
    task.priority = priority
    task.tags = list(tags)
    task.metadata = dict(metadata)
    task.last_updated_at = datetime.now(timezone.utc)
    if hasattr(task_service, "_shared_tasks"):
        task_service._shared_tasks.set(task.task_id, task)
    sync_fn = getattr(task_service, "_sync_task_to_database", None)
    if callable(sync_fn):
        sync_fn(task)
    save_fn = getattr(task_service, "_save_to_persistence", None)
    if callable(save_fn):
        save_fn()


async def _sync_q8_tasks_to_task_service(
    request: Request,
    session_id: str,
    snapshot_map: dict[str, dict[str, Any]],
) -> None:
    task_service = getattr(request.app.state, "task_service", None)
    if task_service is None:
        return

    q8_snapshot = snapshot_map.get("q8")
    if not isinstance(q8_snapshot, dict):
        return

    context_updates = q8_snapshot.get("context_updates")
    context_updates = context_updates if isinstance(context_updates, dict) else {}
    result_payload = q8_snapshot.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}

    objective_profile = (
        context_updates.get("q8_objective_profile")
        or result_payload.get("objective_profile")
        or {}
    )
    objective_profile = objective_profile if isinstance(objective_profile, dict) else {}
    task_queue = (
        context_updates.get("q8_task_queue")
        or result_payload.get("task_queue")
        or {}
    )
    task_queue = task_queue if isinstance(task_queue, dict) else {}

    current_mission = str(
        objective_profile.get("current_mission")
        or objective_profile.get("current_primary_objective")
        or q8_snapshot.get("summary")
        or "Q8 generated task"
    ).strip()

    queue_specs = [
        ("next_self_tasks", TaskStatus.TODO, TaskPriority.HIGH),
        ("blocked_self_tasks", TaskStatus.BLOCKED, TaskPriority.MEDIUM),
        ("proactive_actions", TaskStatus.TODO, TaskPriority.MEDIUM),
    ]

    existing_tasks = []
    list_tasks_fn = getattr(task_service, "list_tasks", None)
    if callable(list_tasks_fn):
        existing_tasks = list(list_tasks_fn() or [])
    existing_by_key: dict[str, ZentexTask] = {}
    for task in existing_tasks:
        metadata = getattr(task, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        if metadata.get("source") == "nine_questions.q8" and metadata.get("session_id") == session_id:
            existing_by_key[str(task.idempotency_key)] = task

    desired_keys: set[str] = set()

    for queue_name, target_status, default_priority in queue_specs:
        for index, item in enumerate(_normalize_q8_task_rows(task_queue.get(queue_name))):
            suffix = _stable_task_suffix(item, index)
            idempotency_key = f"nineq:{session_id}:q8:{queue_name}:{suffix}"
            desired_keys.add(idempotency_key)

            reason = str(item.get("reason") or "").strip()
            remarks = current_mission
            if reason:
                remarks = f"{current_mission}\n阻塞/说明: {reason}"
            metadata = {
                "source": "nine_questions.q8",
                "session_id": session_id,
                "question_id": "q8",
                "queue_name": queue_name,
                "objective": current_mission,
                "trace_id": str(q8_snapshot.get("trace_id") or ""),
            }
            tags = ["nine-questions", "q8", queue_name]
            priority = _coerce_task_priority(item.get("priority"), default_priority)
            existing = existing_by_key.get(idempotency_key)
            if existing is not None:
                if existing.status != target_status:
                    try:
                        task_service.update_task_status(existing.task_id, target_status, remarks)
                    except Exception:
                        logger.warning(
                            "Failed to update synced Q8 task status",
                            extra={"task_id": existing.task_id, "queue_name": queue_name},
                        )
                _sync_task_record_fields(
                    task_service,
                    existing,
                    title=str(item["title"]),
                    remarks=remarks,
                    priority=priority,
                    tags=tags,
                    metadata=metadata,
                )
                continue

            create_task_fn = getattr(task_service, "create_task", None)
            if callable(create_task_fn):
                await create_task_fn(
                    {
                        "idempotency_key": idempotency_key,
                        "title": str(item["title"]),
                        "task_type": TaskType.COGNITIVE_STEP,
                        "status": target_status,
                        "priority": priority,
                        "originator_id": session_id,
                        "remarks": remarks,
                        "tags": tags,
                        "metadata": metadata,
                    }
                )

    for idempotency_key, task in existing_by_key.items():
        if idempotency_key in desired_keys:
            continue
        if task.status in {TaskStatus.TODO, TaskStatus.BLOCKED, TaskStatus.SUSPENDED, TaskStatus.DONE}:
            try:
                task_service.update_task_status(
                    task.task_id,
                    TaskStatus.ARCHIVED,
                    remarks="Archived because Q8 regenerated a new task set.",
                )
            except Exception:
                logger.warning("Failed to archive stale Q8 synced task", extra={"task_id": task.task_id})


# ========== Route Definitions (Facade-First) ==========

@router.get("/nine-questions/status", response_model=NineQuestionsReportPayload)
async def get_nine_questions_status(request: Request):
    """Get lightweight nine-question status (metadata only, no heavy trace details)"""
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)
    
    questions = await build_question_report_items(
        request=request,
        state=state,
        include_trace_detail=False,  # Lightweight - no trace construction
    )
    
    return NineQuestionsReportPayload(
        session_id=session.session_id,
        last_turn_id=str(getattr(session, "last_turn_id", "") or ""),
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=_stringify_timestamp(state.get("last_updated_at") if isinstance(state, dict) else getattr(state, "updated_at", None)),
        last_refresh_reason=(state.get("last_refresh_reason") if isinstance(state, dict) else getattr(state, "last_refresh_reason", None)),
        question_driver_refs=list(state.get("question_driver_refs", []) if isinstance(state, dict) else getattr(state, "question_driver_refs", [])),
        questions=questions,
        trace_ids=build_trace_id_map(state, questions),
    )


@router.get("/nine-questions/latest-report", response_model=NineQuestionsReportPayload)
async def get_latest_nine_questions_report(request: Request):
    """Get latest nine-questions report with full details"""
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)
    
    questions = await build_question_report_items(
        request=request,
        state=state,
        include_trace_detail=True,  # Full report - include traces
    )
    
    return NineQuestionsReportPayload(
        session_id=session.session_id,
        last_turn_id=str(getattr(session, "last_turn_id", "") or ""),
        snapshot_version=int(state.get("snapshot_version", 0) if isinstance(state, dict) else getattr(state, "snapshot_version", 0)),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
        refreshed_at=_stringify_timestamp(state.get("last_updated_at") if isinstance(state, dict) else getattr(state, "updated_at", None)),
        last_refresh_reason=(state.get("last_refresh_reason") if isinstance(state, dict) else getattr(state, "last_refresh_reason", None)),
        question_driver_refs=list(state.get("question_driver_refs", []) if isinstance(state, dict) else getattr(state, "question_driver_refs", [])),
        questions=questions,
        trace_ids=build_trace_id_map(state, questions),
    )


@router.get("/nine-questions/{question_id}")
async def get_nine_question_detail(request: Request, question_id: str):
    """Get detailed information for a specific question"""
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)

    # Build single question item with full trace detail
    question_item = await build_question_report_items(
        request=request,
        state=state,
        question_filter=question_id,
        include_trace_detail=True,
    )

    if not question_item:
        raise HTTPException(status_code=404, detail=f"Question {question_id} has no snapshot")

    return question_item[0]


@router.get("/nine-questions/traces/{trace_id}")
async def get_nine_question_trace_detail(request: Request, trace_id: str):
    """Get detailed trace information for a specific question execution"""
    
    # Check if this is a placeholder trace ID
    if trace_id.endswith(":no-trace") or trace_id == "none" or trace_id == "":
        raise HTTPException(
            status_code=404, 
            detail=f"Trace {trace_id} is a placeholder and has no execution data. This is expected for questions that haven't been executed yet."
        )
    
    session = await get_or_create_session(request)
    
    # Build trace detail
    trace_detail = await build_trace_detail(
        request=request,
        trace_id=trace_id,
        session_id=session.session_id,
    )
    
    if not trace_detail:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    
    return trace_detail


@router.post("/nine-questions/{question_id}/test")
async def run_nine_question_sandbox_test(
    request: Request,
    question_id: str,
    test_request: dict[str, Any],
):
    """Run sandbox test for a specific question with test payload"""
    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")
    
    session = await get_or_create_session(request)
    state = await get_nine_question_state(request, session.session_id)
    
    # Delegate to question-specific test handler
    from .q_handlers import run_question_test
    result = await run_question_test(
        request=request,
        question_id=question_id,
        session_id=session.session_id,
        state=state,
        test_payload=test_request,
    )
    
    return result


@router.post("/nine-questions/{question_id}/run")
async def run_single_nine_question(
    request: Request,
    question_id: str,
    run_request: NineQuestionsRunRequest,
) -> NineQuestionsRunResponse:
    """Re-execute one question and all downstream dependent questions."""
    import asyncio

    if question_id not in [f"q{i}" for i in range(1, 10)]:
        raise HTTPException(status_code=400, detail=f"Invalid question ID: {question_id}")

    session = await get_or_create_session(request)
    facade = get_kernel_service_facade(request)

    try:
        await asyncio.wait_for(
            asyncio.to_thread(facade.rerun_nine_questions_from, session.session_id, question_id),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "single_nine_question_timeout",
                "message": f"{question_id.upper()} 重跑超时（90s），请稍后重试。",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fresh_kernel_state = facade.get_nine_question_state(session.session_id)
    if fresh_kernel_state and get_question_snapshot_map(fresh_kernel_state):
        await _persist_kernel_nine_question_state(request, session.session_id, fresh_kernel_state)

    state = await get_nine_question_state(request, session.session_id)
    snapshot_map = get_question_snapshot_map(state)
    await _sync_q8_tasks_to_task_service(request, session.session_id, snapshot_map)

    return NineQuestionsRunResponse(
        started=question_id in snapshot_map,
        trace_id=str(session.session_id),
        refresh_reason=f"single_nine_question_reexecuted:{question_id}",
        snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
    )


@router.post("/nine-questions/run-all")
async def run_all_nine_questions(
    request: Request,
    run_request: NineQuestionsRunRequest,
) -> NineQuestionsRunResponse:
    """Execute all nine questions end-to-end.

    IMPORTANT: ensure_nine_questions_bootstrap() is a synchronous, potentially
    long-running call (up to 9 × LLM RTT).  It MUST run in a thread-pool
    executor via asyncio.to_thread() to avoid blocking uvicorn's event loop and
    starving other in-flight requests.  Failure to do so causes the worker to
    become unresponsive and eventually crash under load or when a client times
    out and closes the TCP connection mid-call.
    """
    import asyncio

    session = await get_or_create_session(request)
    facade = get_kernel_service_facade(request)

    try:
        # Run the blocking bootstrap off the event loop with a hard 90-second cap.
        # force=True so that an already-completed session can be fully re-run,
        # picking up any code changes since the last execution.
        await asyncio.wait_for(
            asyncio.to_thread(facade.ensure_nine_questions_bootstrap, session.session_id, force=True),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "nine_question_bootstrap_timeout",
                "message": "九问引导超时（90s），请稍后重试。",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Kernel session unavailable for nine-question bootstrap: {exc}") from exc

    # Force-sync kernel's fresh in-memory state into the persistent store,
    # bypassing the stale-data short-circuit in get_nine_question_state().
    fresh_kernel_state = facade.get_nine_question_state(session.session_id)
    if fresh_kernel_state and get_question_snapshot_map(fresh_kernel_state):
        await _persist_kernel_nine_question_state(request, session.session_id, fresh_kernel_state)

    state = await get_nine_question_state(request, session.session_id)
    snapshot_map = get_question_snapshot_map(state)
    await _sync_q8_tasks_to_task_service(request, session.session_id, snapshot_map)

    return NineQuestionsRunResponse(
        started=bool(snapshot_map),
        trace_id=str(session.session_id),
        refresh_reason="all_nine_questions_executed",
        snapshot_version=int(state.get("snapshot_version", len(snapshot_map)) if isinstance(state, dict) else getattr(state, "snapshot_version", len(snapshot_map))),
        revision=int(state.get("revision", 0) if isinstance(state, dict) else getattr(state, "revision", 0)),
    )
