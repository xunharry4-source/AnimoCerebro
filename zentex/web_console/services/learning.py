from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union

from fastapi import Request

from zentex.learning.service import (
    LEARNING_SESSION_ID,
    LearningDirection,
    ReasoningBudget,
    describe_direction,
    run_learning_cycle,
)
from zentex.runtime.models import BrainTranscriptEntryType
from zentex.web_console.contracts.learning import (
    LearningDirectionPlanItem,
    LearningHistoryRow,
    LearningPlanResponse,
    LearningRedlinesSummary,
    LearningRunCycleResponse,
)
from zentex.web_console.dependencies import get_active_model_provider, get_transcript_store


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
            "预算门控；可回滚（rollback_conditions）。事件一律 append-only 写入 BrainTranscriptStore，带 trace_id。"
        ),
        en=(
            "Sandbox/quarantine before promotion; [LLM MANDATORY]—no regex fakery; "
            "reasoning budget gates; explicit rollback_conditions. All steps append-only to BrainTranscriptStore with trace_id."
        ),
    )
    return LearningPlanResponse(directions=directions, redlines=redlines)


def _payload_summary(payload: Dict[str, Any]) -> str:
    if "learning_summary" in payload:
        return str(payload.get("learning_summary") or "")[:500]
    if payload.get("kind") == "aborted":
        return str(payload.get("reason") or payload.get("error") or "aborted")
    return str(payload.get("note") or payload.get("phase") or payload.get("kind") or "")


def build_learning_history(store: Any, *, limit: int = 200) -> List[LearningHistoryRow]:
    rows: List[LearningHistoryRow] = []
    for entry in reversed(store.get_entries_snapshot()):
        if entry.session_id != LEARNING_SESSION_ID:
            continue
        if entry.entry_type != BrainTranscriptEntryType.LEARNING_ENGINE_EVENT:
            continue
        if not isinstance(entry.payload, dict):
            continue
        p = entry.payload
        kind = str(p.get("kind") or "")
        direction = str(p.get("direction") or "")
        verified = bool(p.get("verified")) or bool(p.get("promotion_verified"))
        summary = _payload_summary(p)
        rows.append(
            LearningHistoryRow(
                entry_id=entry.entry_id,
                timestamp=entry.timestamp.astimezone().isoformat(),
                trace_id=entry.trace_id,
                kind=kind,
                direction=direction,
                verified=verified,
                summary=summary,
                architecture_ref=str(p.get("architecture_ref") or ""),
            )
        )
        if len(rows) >= limit:
            break
    return rows


async def execute_learning_cycle(
    request: Request,
    *,
    direction: LearningDirection,
    dry_run: bool,
    load_factor: float,
    extra_context: Optional[Dict[str, Any]] = None,
) -> LearningRunCycleResponse:
    store = get_transcript_store(request)
    provider = None
    if not dry_run:
        provider = get_active_model_provider(request)

    default_budget = int(os.environ.get("ZENTEX_LEARNING_BUDGET_TOKENS", "32000"))
    budget = ReasoningBudget(remaining_tokens=default_budget)

    outcome = await run_learning_cycle(
        store=store,
        direction=direction,
        provider=provider,
        budget=budget,
        load_factor=load_factor,
        dry_run=dry_run,
        extra_context=extra_context,
    )
    return LearningRunCycleResponse(
        trace_id=outcome["trace_id"],
        turn_id="cycle_" + outcome["trace_id"][:8],
        status=outcome["status"],
        detail=outcome.get("detail", {}),
    )
