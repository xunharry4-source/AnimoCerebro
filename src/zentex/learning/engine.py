from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, List, Union
from typing_extensions import Self

from zentex.common.flow_audit import FlowAudit
from zentex.common.startup_markers import log_once
from zentex.foundation.specs.model_provider import ModelProviderSpec
from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection, describe_direction, parse_learning_direction
from zentex.learning.store import LEARNING_EVENT_TYPE, LEARNING_OVERALL_EVENT_TYPE
from zentex.llm.service import LLMService

LEARNING_SESSION_ID = "learning_engine"


class LearningCycleResult(dict):
    """
    Result of a learning cycle, supporting both dict and attribute access.
    """
    def __getattr__(self, name: str) -> Any:
        if name == "lifecycle_status":
            return self.get("status")
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'LearningCycleResult' object has no attribute '{name}'")


def _write_learning_event(
    store: Any,
    *,
    turn_id: str,
    trace_id: str,
    payload: Dict[str, Any],
) -> None:
    if callable(getattr(store, "write_entry", None)):
        store.write_entry(
            session_id=LEARNING_SESSION_ID,
            turn_id=turn_id,
            entry_type=LEARNING_EVENT_TYPE,
            payload=payload,
            source="zentex.learning.engine",
            trace_id=trace_id,
        )
        return
    raise RuntimeError("store must support write_entry() for learning runs")


def _write_learning_overall_record(
    store: Any,
    *,
    turn_id: str,
    trace_id: str,
    direction: LearningDirection,
    status: str,
    summary: str,
    detail: Dict[str, Any],
    audit_payload: Dict[str, Any],
) -> None:
    if not callable(getattr(store, "write_entry", None)):
        raise RuntimeError("store must support write_entry() for learning runs")
    payload = {
        "kind": "overall_record",
        "direction": direction.value,
        "status": status,
        "summary": summary,
        "detail": detail,
        **audit_payload,
    }
    store.write_entry(
        session_id=LEARNING_SESSION_ID,
        turn_id=turn_id,
        entry_type=LEARNING_OVERALL_EVENT_TYPE,
        payload=payload,
        source="zentex.learning.engine",
        trace_id=trace_id,
    )


async def run_learning_cycle(
    *,
    store: Optional[Any] = None,
    direction: LearningDirection,
    provider: Optional[ModelProviderSpec] = None,
    llm_service: Optional[LLMService] = None,
    model_provider_key: Optional[str] = None,
    budget: Optional[ReasoningBudget] = None,
    load_factor: float = 0.0,
    dry_run: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
    audit: Optional[FlowAudit] = None,
) -> Any:
    """
    Main orchestration entry point for Zentex learning.
    """
    log_once(
        "learning.invoked",
        direction=direction.value,
        dry_run=bool(dry_run),
        load_factor=float(load_factor),
    )
    trace_id = str(uuid.uuid4())
    turn_id = "cycle_" + trace_id[:8]
    meta = describe_direction(direction)
    # Audit context merged into every payload when a FlowAudit is provided.
    _audit_payload: Dict[str, Any] = audit.as_payload() if audit is not None else {}

    if store is None:
        raise RuntimeError("store is required for auditable learning runs")

    if store:
        _write_learning_event(
            store,
            turn_id=turn_id,
            trace_id=trace_id,
            payload={
                "kind": "cycle_started",
                "direction": direction.value,
                "architecture_ref": meta["ref"],
                "dry_run": dry_run,
                **_audit_payload,
            },
        )

    if dry_run:
        if store:
            _write_learning_event(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                payload={"kind": "dry_run_ack", **_audit_payload},
            )
            _write_learning_overall_record(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                direction=direction,
                status="dry_run",
                summary=f"{direction.value} learning dry-run acknowledged.",
                detail={"dry_run": True},
                audit_payload=_audit_payload,
            )
        return LearningCycleResult(status="dry_run", trace_id=trace_id)

    if load_factor > 0.8:
        _write_learning_event(
            store,
            turn_id=turn_id,
            trace_id=trace_id,
            payload={"kind": "aborted", "reason": "load_factor too high", **_audit_payload},
        )
        _write_learning_overall_record(
            store,
            turn_id=turn_id,
            trace_id=trace_id,
            direction=direction,
            status="budget_hold",
            summary=f"{direction.value} learning skipped because load_factor was too high.",
            detail={"reason": "load_factor too high", "load_factor": load_factor},
            audit_payload=_audit_payload,
        )
        return LearningCycleResult(status="budget_hold", trace_id=trace_id)

    if direction == LearningDirection.TOOL_SELF_STUDY:
        from zentex.learning.tool_self_study_pipeline import run_dynamic_tool_self_study

        doc_url = (extra_context or {}).get("doc_url")
        if not doc_url or (provider is None and llm_service is None):
            _write_learning_event(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                payload={"kind": "aborted", "reason": "Tool self-study requires 'doc_url' and an LLM service/provider", **_audit_payload},
            )
            _write_learning_overall_record(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                direction=direction,
                status="aborted",
                summary="Tool self-study aborted because required inputs were missing.",
                detail={"reason": "missing_doc_url_or_provider", "doc_url": doc_url},
                audit_payload=_audit_payload,
            )
            return LearningCycleResult(status="aborted", trace_id=trace_id)

        record = await run_dynamic_tool_self_study(
            doc_url=doc_url,
            provider=provider,
            llm_service=llm_service,
            model_provider_key=model_provider_key,
            store=store,
            trace_id=trace_id,
        )

        if record:
            _write_learning_event(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                payload={
                    "kind": "completed",
                    "direction": direction.value,
                    "tool_name": record.tool_name,
                    "summary": f"Self-study from {doc_url} successful.",
                    **_audit_payload,
                },
            )
            _write_learning_overall_record(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                direction=direction,
                status="completed",
                summary=f"Self-study from {doc_url} successful.",
                detail={"tool_name": record.tool_name, "doc_url": doc_url},
                audit_payload=_audit_payload,
            )
            return LearningCycleResult(
                status="completed",
                trace_id=trace_id,
                detail={"tool_name": record.tool_name}
            )
        else:
            _write_learning_event(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                payload={"kind": "aborted", "reason": "Tool self-study pipeline returned no record (sandbox rejection or max attempts exhausted)", **_audit_payload},
            )
            _write_learning_overall_record(
                store,
                turn_id=turn_id,
                trace_id=trace_id,
                direction=direction,
                status="aborted",
                summary="Tool self-study produced no durable knowledge record.",
                detail={"reason": "tool_self_study_pipeline_returned_no_record", "doc_url": doc_url},
                audit_payload=_audit_payload,
            )
            return LearningCycleResult(status="aborted", trace_id=trace_id)

    if direction == LearningDirection.NINE_QUESTION_INTEGRATION:
        learning_detail = dict(extra_context or {})
        question_id = str(learning_detail.get("question_id") or "")
        learning_kind = str(learning_detail.get("learning_kind") or "")
        summary = str(learning_detail.get("summary") or "")
        _write_learning_event(
            store,
            turn_id=turn_id,
            trace_id=trace_id,
            payload={
                "kind": "completed",
                "direction": direction.value,
                "architecture_ref": meta["ref"],
                "question_id": question_id,
                "learning_kind": learning_kind,
                "summary": summary,
                "detail": learning_detail,
                **_audit_payload,
            },
        )
        _write_learning_overall_record(
            store,
            turn_id=turn_id,
            trace_id=trace_id,
            direction=direction,
            status="completed",
            summary=summary or f"{question_id or 'unknown'} learning recorded.",
            detail=learning_detail,
            audit_payload=_audit_payload,
        )
        return LearningCycleResult(
            status="completed",
            trace_id=trace_id,
            detail=learning_detail,
        )

    _write_learning_overall_record(
        store,
        turn_id=turn_id,
        trace_id=trace_id,
        direction=direction,
        status="unknown_direction",
        summary=f"{direction.value} learning direction is not implemented.",
        detail={},
        audit_payload=_audit_payload,
    )
    return LearningCycleResult(status="unknown_direction", trace_id=trace_id)


# ────────────────────────────────────────────────────────────────
#  通用对外方法 / Universal Public API
# ────────────────────────────────────────────────────────────────


async def start_learning(
    *,
    store: Optional[Any] = None,
    direction: Union[str, LearningDirection],
    provider: Optional[ModelProviderSpec] = None,
    llm_service: Optional[LLMService] = None,
    model_provider_key: Optional[str] = None,
    doc_url: Optional[str] = None,
    dry_run: bool = False,
    load_factor: float = 0.0,
    audit: Optional[FlowAudit] = None,
) -> Any:
    """
    统一的学习启动入口。

    外部模块（Web API、Agent、CLI）通过此方法触发学习循环，
    无需直接构造 run_learning_cycle 的复杂参数。

    Args:
        store:        LearningStore 或兼容存储实例。
        direction:    学习方向，可传字符串（如 "tool_self_study"）或枚举。
        provider:     模型 Provider（工具自学等方向必需）。
        doc_url:      文档 URL（工具自学方向必需）。
        dry_run:      是否为模拟运行。
        load_factor:  当前系统负载因子（0.0 ~ 1.0）。

    Returns:
        LearningCycleResult 实例。
    """
    if isinstance(direction, str):
        try:
            direction = parse_learning_direction(direction)
        except ValueError:
            return LearningCycleResult(
                status="invalid_direction",
                trace_id=str(uuid.uuid4()),
                detail={"error": f"Unknown direction: {direction}"},
            )

    extra_context: Optional[Dict[str, Any]] = None
    if doc_url:
        extra_context = {"doc_url": doc_url}

    if store is None:
        raise RuntimeError("store is required for start_learning")

    return await run_learning_cycle(
        store=store,
        direction=direction,
        provider=provider,
        llm_service=llm_service,
        model_provider_key=model_provider_key,
        dry_run=dry_run,
        load_factor=load_factor,
        extra_context=extra_context,
        audit=audit,
    )


def list_available_directions() -> list[Dict[str, Any]]:
    """
    列出所有可用的学习方向及其描述。

    适用于前端下拉菜单或 CLI 提示。

    Returns:
        每个方向的 ID、名称和描述列表。
    """
    directions = []
    for d in LearningDirection:
        meta = describe_direction(d)
        directions.append({
            "direction_id": d.value,
            "ref": meta.get("ref", "UNKNOWN"),
            "description": meta.get("description", "N/A"),
        })
    return directions


def get_learning_status(
    store: Optional[Any] = None,
    *,
    trace_id: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    查询学习引擎的运行状态与最近的学习事件日志。

    Args:
        store:    LearningStore 或兼容存储实例。
        trace_id: 可选的追踪 ID，用于过滤特定学习周期。
        limit:    返回的最近事件数量上限。

    Returns:
        包含可用方向、最近事件等信息的字典。
    """
    if store is None:
        raise RuntimeError("store is required for get_learning_status")

    entries = store.query_by_session(LEARNING_SESSION_ID, limit=max(limit * 5, 200))
    if trace_id:
        entries = [e for e in entries if e.trace_id == trace_id]
    recent = sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]

    return {
        "status": "ok",
        "available_directions": list_available_directions(),
        "recent_events_count": len(entries),
        "entries": len(entries),
        "recent_events": [
            {
                "entry_id": e.entry_id,
                "trace_id": e.trace_id,
                "entry_type": str(getattr(getattr(e, "entry_type", None), "value", getattr(e, "entry_type", "")) or ""),
                "payload": e.payload,
                "created_at": str(e.timestamp),
            }
            for e in recent
        ],
    }


# ════════════════════════════════════════════════════════════════════
#  模块说明 / Module Documentation
# ════════════════════════════════════════════════════════════════════
#
#  zentex.learning.engine — 学习引擎核心编排
#
#  本模块是 Zentex 自主学习系统的主编排层，负责协调学习方向路由、
#  预算守卫、以及学习结果的 Transcript 审计记录。
#
#  架构概览：
#
#    ┌──────────────────┐
#    │  start_learning() │  ◄── 统一对外入口
#    └────────┬─────────┘
#             │
#    ┌────────▼─────────┐
#    │ run_learning_cycle│  ◄── 内部编排（方向路由 + 预算检查）
#    └────────┬─────────┘
#             │
#    ┌────────▼──────────────────────────────┐
#    │  Tool Self-Study Pipeline             │
#    │  (DSPy Distiller → Critic → Sandbox)  │
#    └───────────────────────────────────────┘
#
#  通用对外方法（Universal Public API）：
#
#    start_learning()              — 统一学习启动入口
#    list_available_directions()   — 列出可用学习方向
#    get_learning_status()         — 查询学习状态与最近事件日志
#    run_learning_cycle()          — 底层编排（通常由 start_learning 代理调用）
#
#  学习方向（Learning Directions）：
#
#    TOOL_SELF_STUDY      — 基于文档的自主工具发现与验证
#    G24_CURIOSITY        — 好奇心驱动的探索性数据摄入（规划中）
#
# ════════════════════════════════════════════════════════════════════
