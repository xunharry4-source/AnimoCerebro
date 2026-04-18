"""
Learning Router — /api/web/learning/* endpoints.

RESPONSIBILITY:
  Exposes learning history, plan, and cycle-execution endpoints for the
  web console learning panel.

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  get_transcript_store() may return None when the kernel service does not
  have a transcript store (e.g. during early startup).  The /learning/history
  handler checks for None and raises HTTPException(503) rather than letting
  build_learning_history crash with AttributeError.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from zentex.learning.service import LearningDirection
from zentex.web_console.contracts.learning import (
    LearningHistoryResponse,
    LearningPlanResponse,
    LearningRunCycleRequest,
    LearningRunCycleResponse,
)
from zentex.web_console.dependencies import get_transcript_store
from zentex.web_console.services.learning import (
    build_learning_history,
    build_learning_plan,
    execute_learning_cycle,
)

router = APIRouter()


@router.get("/learning/plan", response_model=LearningPlanResponse)
def learning_plan() -> LearningPlanResponse:
    return build_learning_plan()


@router.get("/learning/history", response_model=LearningHistoryResponse)
def learning_history(
    request: Request,
    limit: int = Query(default=200, ge=1, le=2000),
) -> LearningHistoryResponse:
    store = get_transcript_store(request)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "transcript_store_unavailable",
                "message": "TranscriptStore 未初始化，学习历史不可用。",
            },
        )
    rows = build_learning_history(store, limit=limit)
    return LearningHistoryResponse(rows=rows)


@router.post("/learning/run-cycle", response_model=LearningRunCycleResponse)
async def learning_run_cycle(request: Request, body: LearningRunCycleRequest) -> LearningRunCycleResponse:
    if not body.dry_run:
        raise HTTPException(
            status_code=410,
            detail={
                "error": "web_console_llm_invocation_removed",
                "message": "web-console 不再承接非 dry-run 的 learning cycle；如需真实 LLM 执行，请从后台核心模块直接调用。",
            },
        )
    try:
        direction = LearningDirection(body.direction)
    except ValueError as exc:
        allowed = ", ".join(d.value for d in LearningDirection)
        raise HTTPException(status_code=400, detail=f"Invalid direction. Allowed: {allowed}") from exc

    return await execute_learning_cycle(
        request,
        direction=direction,
        dry_run=body.dry_run,
        load_factor=body.load_factor,
        extra_context=body.extra_context,
    )
