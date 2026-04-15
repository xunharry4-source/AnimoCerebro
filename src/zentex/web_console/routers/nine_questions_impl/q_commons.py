"""Common Nine-Questions Service Layer

Provides shared utilities for:
- Session management (get/create)
- State management (get/update)
- Question report building
- Common error handling
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request

from zentex.web_console.dependencies import (
    get_session_manager,
    get_nine_question_state_manager,
    get_kernel_service_facade,
    get_runtime,
)
from zentex.web_console.contracts.nine_questions import NineQuestionReportItem

logger = logging.getLogger(__name__)


def _state_has_question_data(state: Any) -> bool:
    snapshot_map = get_question_snapshot_map(state)
    return bool(snapshot_map)


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
    runtime = get_runtime(request)
    session_mgr = get_session_manager(request)
    workspace = getattr(session, "workspace", None) or getattr(request.app.state, "default_workspace", "/workspace")

    session_id = getattr(session, "session_id", None)
    if session_id and runtime.get_session_meta(session_id):
        request.app.state.session = session
        request.app.state.active_session = session
        return session

    kernel_session_id: str | None = None
    active_kernel_sessions = runtime.list_active_sessions()
    if active_kernel_sessions:
        kernel_session_id = active_kernel_sessions[0]
    else:
        kernel_session_id = runtime.create_session(user_id="web-console")

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

    if persisted_state is not None and _state_has_question_data(persisted_state) and not _state_requires_refresh(persisted_state):
        return persisted_state

    full_state = facade.get_nine_question_state(session_id)
    if _state_has_question_data(full_state):
        await _persist_kernel_nine_question_state(request, session_id, full_state)
        return full_state

    latest_persisted_state = await state_mgr.get_latest_populated_state()
    if latest_persisted_state is not None and _state_has_question_data(latest_persisted_state) and not _state_requires_refresh(latest_persisted_state):
        if persisted_state is None or not _state_has_question_data(persisted_state):
            if persisted_state is None:
                await state_mgr.bootstrap_state(session_id)
            await state_mgr.update_state(
                session_id,
                question_snapshots=get_question_snapshot_map(latest_persisted_state),
                snapshot_version=int(getattr(latest_persisted_state, "snapshot_version", 9)),
                last_refresh_reason=getattr(latest_persisted_state, "last_refresh_reason", None),
                dirty_questions=[],
            )
        return latest_persisted_state

    runtime = get_runtime(request)
    try:
        runtime.ensure_nine_questions_bootstrap(session_id)
    except ValueError:
        logger.warning("Kernel nine-question bootstrap skipped for unknown session %s", session_id)
    except Exception as exc:
        logger.warning("Kernel nine-question bootstrap failed for %s: %s", session_id, exc)

    full_state = facade.get_nine_question_state(session_id)
    if _state_has_question_data(full_state):
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
    question_ids = [question_filter] if question_filter else [f"q{i}" for i in range(1, 10)]
    
    for question_id in question_ids:
        snapshot = snapshot_map.get(question_id)
        if not snapshot or not isinstance(snapshot, dict):
            continue
        
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
        
        item = NineQuestionReportItem(
            question_id=question_id,
            title=QUESTION_TITLES.get(question_id, question_id),
            tool_id=str(snapshot.get("tool_id") or f"nine_questions.{question_id}"),
            summary=snapshot.get("summary", ""),
            confidence=float(snapshot.get("confidence") or 0.0),
            result=snapshot.get("result"),
            context_updates=snapshot.get("context_updates", {}) or {},
            trace_id=str(trace_id or f"{question_id}:no-trace"),
            timestamp=str(snapshot.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        )
        items.append(item)
    
    return items


def validate_question_id(question_id: str) -> bool:
    """Validate if question_id is in valid format (q1-q9)"""
    return question_id in [f"q{i}" for i in range(1, 10)]
