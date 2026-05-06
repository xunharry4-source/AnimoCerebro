from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from zentex.common.flow_audit import FlowAudit
from zentex.reflection.models import ReflectionTrigger
from zentex.reflection.nine_question_effectiveness import (
    dependent_questions,
    run_question_reflection,
)
from zentex.web_console.dependencies import (
    get_reflection_service,
    get_runtime,
    get_upgrade_execution_service,
)
from zentex.web_console.routers.module_log_writer import record_module_management_log


router = APIRouter(prefix="/reflections", tags=["nine-question-reflections"])

_VALID_QUESTION_IDS = {f"q{i}" for i in range(1, 10)}
_force_reflection_lock = Lock()


class ForceReflectionRequest(BaseModel):
    include_dependencies: bool = Field(default=True)


class ReflectionMaintenanceTriggerRequest(BaseModel):
    force: bool = Field(default=True)


@router.post("/{question_id}/force")
def force_reflect_question(
    question_id: str,
    body: ForceReflectionRequest,
    request: Request,
    runtime: Any = Depends(get_runtime),
    upgrade_execution_service: Any = Depends(get_upgrade_execution_service),
    reflection_service: Any = Depends(get_reflection_service),
) -> dict[str, Any]:
    qid = str(question_id).strip().lower()
    if qid not in _VALID_QUESTION_IDS:
        raise HTTPException(status_code=400, detail=f"Invalid question_id: {question_id}")

    state = getattr(runtime, "nine_question_state", None)
    if state is None:
        raise HTTPException(status_code=503, detail="NineQuestionState is not available")

    state_payload = state.to_payload() if hasattr(state, "to_payload") else {}

    targets = dependent_questions(qid) if body.include_dependencies else [qid]

    results: list[dict[str, Any]] = []
    audit_service = getattr(request.app.state, "audit_service", None)
    audit = FlowAudit.new("reflection", source_module=__name__, question_driver_refs=targets)
    if audit_service:
        audit_service.record_flow_start(audit)
    with _force_reflection_lock:
        try:
            for target_q in targets:
                result = run_question_reflection(
                    reflection_service=reflection_service,
                    question_id=target_q,
                    state_payload=state_payload,
                    scope="question_with_dependencies" if body.include_dependencies else "single_question",
                    trigger="manual_force",
                    upgrade_execution_service=upgrade_execution_service,
                )
                results.append(result)
        except Exception:
            if audit_service:
                audit_service.record_flow_end(audit, status="failed")
            raise
    if audit_service:
        audit_service.record_flow_end(audit, status="completed")

    return {
        "started": True,
        "question_id": qid,
        "scope": "question_with_dependencies" if body.include_dependencies else "single_question",
        "count": len(results),
        "results": results,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/maintenance/trigger")
def trigger_reflection_maintenance(
    request: Request,
    body: ReflectionMaintenanceTriggerRequest | None = None,
    reflection_service: Any = Depends(get_reflection_service),
) -> dict[str, Any]:
    if not callable(getattr(reflection_service, "trigger_memory_aware_maintenance", None)):
        raise HTTPException(status_code=503, detail="Reflection service does not expose memory-aware maintenance.")
    force = True if body is None else bool(body.force)
    try:
        result = reflection_service.trigger_memory_aware_maintenance(
            operator="web-console-operator",
            trigger=ReflectionTrigger.MANUAL,
            force=force,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "reflection_maintenance_failed",
                "operator_message": f"反思自动整理触发失败：{exc}",
            },
        ) from exc
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
    record_module_management_log(
        request,
        source_module="reflection",
        module_label="反思模块",
        action="force_auto_organize" if force else "manual_maintenance",
        action_label="强制启动自动整理" if force else "手动启动整理",
        object_id=str(payload.get("trace_id") or payload.get("generated_reflection_id") or "reflection-maintenance"),
        object_label="记忆感知反思维护",
        before_status="idle",
        after_status="completed",
        reason="操作员从反思页面触发自动整理",
        details={**payload, "force": force},
        operator_id="web-console-operator",
        status="completed",
    )
    return {"started": True, "forced": force, **payload}


@router.get("")
def list_nine_question_reflections(
    q_id: Optional[str] = None,
    limit: int = 50,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    date: Optional[str] = None,
    source: Optional[str] = None,
    reflection_service: Any = Depends(get_reflection_service),
) -> dict[str, Any]:
    effective_page_size = max(1, min(int(page_size or limit or 25), 200))
    if limit != 50 and page_size == 25:
        effective_page_size = max(1, min(int(limit), 200))
    effective_page = max(1, int(page))
    filters: dict[str, Any] = {
        "question_scope": "nine_questions",
    }
    if q_id:
        filters["question_id"] = str(q_id).strip().lower()
    if date:
        try:
            filters["date"] = date_type.fromisoformat(str(date)).isoformat()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date: {date}. Expected YYYY-MM-DD.") from exc
    if source:
        normalized_source = str(source).strip().lower()
        if normalized_source not in {"plugin", "all", "nine_questions"}:
            raise HTTPException(status_code=400, detail="Invalid source. Allowed: all, plugin, nine_questions.")
        if normalized_source in {"plugin", "all"} and not date:
            raise HTTPException(
                status_code=400,
                detail="date is required when source is plugin or all. Expected YYYY-MM-DD.",
            )
        if normalized_source == "plugin":
            filters["source"] = "plugin"
            if not q_id:
                filters.pop("question_scope", None)
        if normalized_source == "all":
            filters.pop("question_scope", None)
    offset = (effective_page - 1) * effective_page_size
    if not callable(getattr(reflection_service, "query_reflections_page", None)):
        raise HTTPException(status_code=503, detail="Reflection service does not expose strict paginated queries.")
    if not callable(getattr(reflection_service, "count_reflections", None)):
        raise HTTPException(status_code=503, detail="Reflection service does not expose strict reflection counts.")
    total_items = int(reflection_service.count_reflections(filters=filters))
    reflections = reflection_service.query_reflections_page(
        filters=filters,
        limit=effective_page_size,
        offset=offset,
    )
    items = [record.model_dump(mode="json") for record in reflections]
    total_pages = max((total_items + effective_page_size - 1) // effective_page_size, 1)

    return {
        "total": total_items,
        "page": effective_page,
        "page_size": effective_page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "date": filters.get("date"),
        "source": source or "nine_questions",
        "database_backed": True,
        "items": items,
    }


@router.get("/{reflection_id}")
def get_nine_question_reflection(
    reflection_id: str,
    reflection_service: Any = Depends(get_reflection_service),
) -> dict[str, Any]:
    try:
        record = reflection_service.get_reflection(reflection_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail=f"Reflection not found: {reflection_id}")
    if record is None:
        raise HTTPException(status_code=404, detail=f"Reflection not found: {reflection_id}")
    return record.model_dump(mode="json")
