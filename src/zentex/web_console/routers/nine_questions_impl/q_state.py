from __future__ import annotations
"""Nine-question session/state access helpers."""


import logging
import asyncio
import time
from typing import Any

from fastapi import HTTPException, Request

from zentex.nine_questions.service import NineQuestionService
from zentex.web_console.dependencies import (
    get_kernel_service_facade,
    get_nine_question_state_manager,
    get_session_manager,
)
from zentex.kernel.workspace_policy import resolve_q1_workspace_root

logger = logging.getLogger(__name__)
_SESSION_KERNEL_STEP_TIMEOUT_SECONDS = 15.0


async def _run_sync_session_step(label: str, fn: Any) -> Any:
    started = time.monotonic()
    logger.info("[nine-questions] session step start step=%s", label)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(fn),
            timeout=_SESSION_KERNEL_STEP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[nine-questions] session step timeout step=%s timeout=%.1fs elapsed=%.3fs",
            label,
            _SESSION_KERNEL_STEP_TIMEOUT_SECONDS,
            time.monotonic() - started,
        )
        raise
    except Exception:
        logger.exception(
            "[nine-questions] session step failed step=%s elapsed=%.3fs",
            label,
            time.monotonic() - started,
        )
        raise
    logger.info(
        "[nine-questions] session step complete step=%s elapsed=%.3fs",
        label,
        time.monotonic() - started,
    )
    return result


def _get_nine_question_service(request: Request) -> NineQuestionService:
    started = time.monotonic()
    logger.info("[nine-questions] service resolve start")
    facade = get_kernel_service_facade(request)
    state_manager = get_nine_question_state_manager(request)
    logger.info("[nine-questions] service resolve complete elapsed=%.3fs", time.monotonic() - started)
    return NineQuestionService(
        facade=facade,
        state_manager=state_manager,
    )


async def _persist_kernel_nine_question_state(
    request: Request,
    state: Any,
) -> None:
    service = _get_nine_question_service(request)
    await service.persist_kernel_state(state)


async def _ensure_kernel_backed_session(request: Request, session: Any) -> Any:
    facade = get_kernel_service_facade(request)
    session_mgr = get_session_manager(request)
    started = time.monotonic()
    logger.info(
        "[nine-questions] ensure kernel-backed session start web_session_id=%s",
        getattr(session, "session_id", None),
    )
    workspace = getattr(session, "workspace", None) or str(
        resolve_q1_workspace_root(None, facade.get_workspace_store())
    )

    session_id = getattr(session, "session_id", None)
    if session_id and await _run_sync_session_step(
        "kernel.get_session_meta",
        lambda: facade.get_session_meta(session_id),
    ):
        request.app.state.session = session
        request.app.state.active_session = session
        logger.info(
            "[nine-questions] ensure kernel-backed session reused web_session_id=%s elapsed=%.3fs",
            session_id,
            time.monotonic() - started,
        )
        return session

    active_kernel_sessions = await _run_sync_session_step(
        "kernel.list_active_sessions",
        facade.list_active_sessions,
    )
    if active_kernel_sessions:
        kernel_session_id = active_kernel_sessions[0]
    else:
        kernel_session_id = await _run_sync_session_step(
            "kernel.create_kernel_session",
            lambda: facade.create_kernel_session(user_id="web-console"),
        )

    try:
        logger.info("[nine-questions] session manager get_active_session start session_id=%s", kernel_session_id)
        resolved = await session_mgr.get_active_session(kernel_session_id)
    except ValueError:
        logger.info("[nine-questions] session manager create_session start session_id=%s", kernel_session_id)
        resolved = await session_mgr.create_session(workspace=workspace, session_id=kernel_session_id)

    request.app.state.session = resolved
    request.app.state.active_session = resolved
    logger.info(
        "[nine-questions] ensure kernel-backed session complete kernel_session_id=%s elapsed=%.3fs",
        kernel_session_id,
        time.monotonic() - started,
    )
    return resolved


async def get_or_create_session(request: Request) -> Any:
    started = time.monotonic()
    logger.info("[nine-questions] get_or_create_session start")
    session_mgr = get_session_manager(request)
    if not session_mgr:
        raise HTTPException(status_code=503, detail="SessionManager not available")

    try:
        session = getattr(request.app.state, "session", None) or getattr(request.app.state, "active_session", None)
        session_id = getattr(session, "session_id", None) if session is not None else None
        if session_id:
            try:
                logger.info("[nine-questions] existing app session found session_id=%s", session_id)
                resolved = await session_mgr.get_active_session(session_id)
                return await _ensure_kernel_backed_session(request, resolved)
            except ValueError:
                logger.info("Discarding stale web-console session %s for nine-question flow", session_id)

        logger.info("[nine-questions] session manager list_active_sessions start")
        active_sessions = await session_mgr.list_active_sessions()
        logger.info("[nine-questions] session manager list_active_sessions complete count=%d", len(active_sessions))
        if active_sessions:
            resolved = active_sessions[0]
            return await _ensure_kernel_backed_session(request, resolved)

        workspace = str(resolve_q1_workspace_root(None, get_kernel_service_facade(request).get_workspace_store()))
        logger.info("[nine-questions] session manager create_session start workspace=%s", workspace)
        session = await session_mgr.create_session(workspace=workspace)
        resolved = await _ensure_kernel_backed_session(request, session)
        logger.info("[nine-questions] get_or_create_session complete elapsed=%.3fs", time.monotonic() - started)
        return resolved
    except Exception as e:
        logger.error("Session management error: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to manage session")


async def get_nine_question_state(request: Request) -> Any:
    service = _get_nine_question_service(request)
    try:
        return await service.get_state()
    except Exception as e:
        logger.error("State management error: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to manage state")


def get_question_snapshot_map(state: Any) -> dict[str, dict[str, Any]]:
    if isinstance(state, dict):
        snapshots = state.get("question_snapshots")
        if isinstance(snapshots, dict):
            return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
        return {}

    snapshots = getattr(state, "question_snapshots", None)
    if isinstance(snapshots, dict):
        return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
    return {}


def build_trace_id_map(state: Any, items: list[Any]) -> dict[str, str]:
    raw_trace_ids = {
        qid: str(item.get("trace_id") or "")
        for qid, item in get_question_snapshot_map(state).items()
    }
    for item in items:
        raw_trace_ids[item.question_id] = item.trace_id
    return raw_trace_ids


def validate_question_id(question_id: str) -> bool:
    return question_id in [f"q{i}" for i in range(1, 10)]


def _state_has_question_data(state: Any) -> bool:
    return bool(get_question_snapshot_map(state))


def _state_has_complete_question_data(state: Any) -> bool:
    return NineQuestionService.state_has_complete_question_data(state)


def _state_requires_refresh(state: Any) -> bool:
    if isinstance(state, dict):
        return bool(state.get("dirty_questions") or [])
    return bool(getattr(state, "dirty_questions", []) or [])
