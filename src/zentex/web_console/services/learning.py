from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import Request

from zentex.common.flow_audit import FlowAudit
from zentex.learning.service import (
    LEARNING_SESSION_ID,
    LearningDirection,
    ReasoningBudget,
    describe_direction,
    run_learning_cycle,
)
from zentex.web_console.contracts.learning import (
    LearningDirectionPlanItem,
    LearningHistoryRow,
    LearningHistoryResponse,
    LearningPlanResponse,
    LearningRedlinesSummary,
    LearningRunCycleResponse,
)
def _entry_type_value(entry: Any) -> str:
    entry_type = getattr(entry, "entry_type", None)
    normalized = str(getattr(entry_type, "value", entry_type) or "")
    if normalized:
        return normalized
    payload = getattr(entry, "payload", None)
    if isinstance(payload, dict):
        return str(payload.get("entry_type") or "")
    return ""


def _entry_timestamp_iso(entry: Any) -> str:
    raw_timestamp = getattr(entry, "timestamp", None)
    if isinstance(raw_timestamp, datetime):
        return raw_timestamp.astimezone().isoformat()
    if isinstance(raw_timestamp, str) and raw_timestamp.strip():
        try:
            return datetime.fromisoformat(raw_timestamp).astimezone().isoformat()
        except ValueError:
            return raw_timestamp
    return ""


def build_learning_plan() -> LearningPlanResponse:
    directions: List[LearningDirectionPlanItem] = []
    for d in LearningDirection:
        meta = describe_direction(d)
        
        fallback_title = meta.get("title_zh") or meta.get("title_en") or d.name
        fallback_desc = meta.get("description") or "暂无可用描述 / No description available"

        directions.append(
            LearningDirectionPlanItem(
                id=d.value,
                architecture_ref=meta.get("ref", "UNKNOWN"),
                title_zh=meta.get("title_zh", fallback_title),
                title_en=meta.get("title_en", fallback_title),
                body_zh=meta.get("body_zh", fallback_desc),
                body_en=meta.get("body_en", fallback_desc),
            )
        )
    redlines = LearningRedlinesSummary(
        zh=(
            "安全隔离与沙箱验证；[LLM MANDATORY] 提纯/理解/总结须走 ModelProvider，失败即中断；"
            "预算门控；可回滚（rollback_conditions）。事件一律 append-only 写入 LearningStore，带 trace_id。"
        ),
        en=(
            "Sandbox/quarantine before promotion; [LLM MANDATORY]—no regex fakery; "
            "reasoning budget gates; explicit rollback_conditions. All steps append-only to LearningStore with trace_id."
        ),
    )
    return LearningPlanResponse(directions=directions, redlines=redlines)


def _payload_summary(payload: Dict[str, Any]) -> str:
    if "learning_summary" in payload:
        return str(payload.get("learning_summary") or "")[:500]
    if "summary" in payload:
        return str(payload.get("summary") or "")[:500]
    if payload.get("kind") == "aborted":
        return str(payload.get("reason") or payload.get("error") or "aborted")
    return str(payload.get("note") or payload.get("phase") or payload.get("kind") or "")


def build_learning_history(service: Any, *, limit: int = 200) -> List[LearningHistoryRow]:
    return build_learning_history_page(service, page=1, page_size=limit).rows


def build_learning_history_page(service: Any, *, page: int = 1, page_size: int = 200) -> LearningHistoryResponse:
    rows: List[LearningHistoryRow] = []
    if not callable(getattr(service, "query_history_entries", None)):
        raise RuntimeError("learning service does not expose query_history_entries()")
    if not callable(getattr(service, "count_history_entries", None)):
        raise RuntimeError("learning service does not expose count_history_entries()")
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 500))
    total_items = int(service.count_history_entries())
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    offset = (page - 1) * page_size
    entries = list(service.query_history_entries(limit=page_size, offset=offset))
    for entry in entries:
        if entry.session_id != LEARNING_SESSION_ID:
            continue
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        if not isinstance(payload, dict):
            continue
        p = payload
        kind = str(p.get("kind") or "")
        direction = str(p.get("direction") or "")
        verified = bool(p.get("verified")) or bool(p.get("promotion_verified"))
        summary = _payload_summary(p)
        raw_question_refs = p.get("question_driver_refs")
        if not isinstance(raw_question_refs, list):
            caller_context = p.get("caller_context")
            if isinstance(caller_context, dict):
                raw_question_refs = caller_context.get("question_driver_refs")
        if not isinstance(raw_question_refs, list):
            detail = p.get("detail")
            if isinstance(detail, dict):
                raw_question_refs = detail.get("question_driver_refs")
        question_driver_refs = [
            str(item).strip()
            for item in (raw_question_refs or [])
            if str(item).strip()
        ]
        rows.append(
            LearningHistoryRow(
                entry_id=entry.entry_id,
                timestamp=_entry_timestamp_iso(entry),
                trace_id=entry.trace_id,
                session_id=str(getattr(entry, "session_id", "") or ""),
                replay_event_id=entry.trace_id,
                kind=kind,
                direction=direction,
                verified=verified,
                summary=summary,
                architecture_ref=str(p.get("architecture_ref") or ""),
                question_driver_refs=question_driver_refs,
            )
        )
    return LearningHistoryResponse(
        rows=rows,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


async def execute_learning_cycle(
    request: Request,
    *,
    direction: LearningDirection,
    dry_run: bool,
    load_factor: float,
    extra_context: Optional[Dict[str, Any]] = None,
) -> LearningRunCycleResponse:
    learning_service = getattr(request.app.state, "learning_service", None)

    default_budget = int(os.environ.get("ZENTEX_LEARNING_BUDGET_TOKENS", "32000"))
    budget = ReasoningBudget(remaining_tokens=default_budget)

    audit = FlowAudit.new("learning", source_module="zentex.web_console.services.learning")
    audit_service = getattr(request.app.state, "audit_service", None)

    if callable(getattr(audit_service, "record_flow_start", None)):
        audit_service.record_flow_start(audit)
    try:
        outcome = await run_learning_cycle(
            store=getattr(learning_service, "store", None),
            direction=direction,
            provider=None,
            llm_service=None,
            model_provider_key=None,
            budget=budget,
            load_factor=load_factor,
            dry_run=dry_run,
            extra_context=extra_context,
            audit=audit,
        )
    except Exception:
        if callable(getattr(audit_service, "record_flow_end", None)):
            audit_service.record_flow_end(audit, status="failed")
        raise
    if callable(getattr(audit_service, "record_flow_end", None)):
        audit_service.record_flow_end(audit, status="completed")
    return LearningRunCycleResponse(
        trace_id=outcome["trace_id"],
        turn_id="cycle_" + outcome["trace_id"][:8],
        status=outcome["status"],
        detail=outcome.get("detail", {}),
    )
