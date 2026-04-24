from __future__ import annotations
"""Nine-question session/state access helpers."""


import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request

from zentex.nine_questions.service import NineQuestionService
from zentex.web_console.dependencies import (
    get_kernel_service_facade,
    get_nine_question_state_manager,
    get_session_manager,
)

logger = logging.getLogger(__name__)


def _get_nine_question_service(request: Request) -> NineQuestionService:
    return NineQuestionService(
        facade=get_kernel_service_facade(request),
        state_manager=get_nine_question_state_manager(request),
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
    workspace = getattr(session, "workspace", None) or getattr(request.app.state, "default_workspace", "/workspace")

    session_id = getattr(session, "session_id", None)
    if session_id and facade.get_session_meta(session_id):
        request.app.state.session = session
        request.app.state.active_session = session
        return session

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
    session_mgr = get_session_manager(request)
    if not session_mgr:
        raise HTTPException(status_code=503, detail="SessionManager not available")

    try:
        session = getattr(request.app.state, "session", None) or getattr(request.app.state, "active_session", None)
        session_id = getattr(session, "session_id", None) if session is not None else None
        if session_id:
            try:
                resolved = await session_mgr.get_active_session(session_id)
                return await _ensure_kernel_backed_session(request, resolved)
            except ValueError:
                logger.info("Discarding stale web-console session %s for nine-question flow", session_id)

        active_sessions = await session_mgr.list_active_sessions()
        if active_sessions:
            resolved = active_sessions[0]
            return await _ensure_kernel_backed_session(request, resolved)

        workspace = getattr(request.app.state, "default_workspace", "/workspace")
        session = await session_mgr.create_session(workspace=workspace)
        return await _ensure_kernel_backed_session(request, session)
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
