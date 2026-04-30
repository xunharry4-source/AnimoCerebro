from __future__ import annotations
"""
Learning Router — /api/web/learning/* endpoints.

RESPONSIBILITY:
  Exposes learning history, plan, and cycle-execution endpoints for the
  web console learning panel.

FAIL-CLOSED CONTRACT (Zentex Codex §1):
  learning/service.py is the only public learning entrypoint. The /learning/history
  handler must read the canonical learning service from app.state and fail closed
  if that service is unavailable.
"""


from fastapi import APIRouter, HTTPException, Query, Request

from zentex.common.flow_audit import FlowAudit
from zentex.learning.service import LearningDirection
from zentex.web_console.contracts.learning import (
    LearningHistoryResponse,
    LearningPlanResponse,
    LearningRunCycleRequest,
    LearningRunCycleResponse,
)
from zentex.web_console.services.learning import (
    build_learning_history_page,
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=500),
) -> LearningHistoryResponse:
    learning_service = getattr(request.app.state, "learning_service", None)
    if learning_service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "learning_service_unavailable",
                "message": "LearningService 未初始化，学习历史不可用。",
            },
        )
    return build_learning_history_page(learning_service, page=page, page_size=page_size)


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

    raw_question_refs = (body.extra_context or {}).get("question_driver_refs")
    question_refs = [str(item) for item in raw_question_refs] if isinstance(raw_question_refs, list) else []
    audit_service = getattr(request.app.state, "audit_service", None)
    audit = FlowAudit.new("learning", source_module=__name__, question_driver_refs=question_refs)
    if audit_service:
        audit_service.record_flow_start(audit)
    try:
        result = await execute_learning_cycle(
            request,
            direction=direction,
            dry_run=body.dry_run,
            load_factor=body.load_factor,
            extra_context={**(body.extra_context or {}), **audit.as_payload()},
        )
    except Exception:
        if audit_service:
            audit_service.record_flow_end(audit, status="failed")
        raise
    if audit_service:
        audit_service.record_flow_end(audit, status="completed")
    return result
