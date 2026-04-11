from __future__ import annotations

import uuid
from typing import Any, Dict, Optional
from typing_extensions import Self

from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection, describe_direction
from zentex.runtime.service import get_runtime_service
from zentex.runtime.transcript import BrainTranscriptEntryType

LEARNING_SESSION_ID = "learning_engine"


class LearningCycleResult(dict):
    """
    Result of a learning cycle, supporting both dict and attribute access.
    """
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'LearningCycleResult' object has no attribute '{name}'")


async def run_learning_cycle(
    *,
    store: Optional[Any] = None,
    direction: LearningDirection,
    provider: Optional[ModelProviderSpec] = None,
    budget: Optional[ReasoningBudget] = None,
    load_factor: float = 0.0,
    dry_run: bool = False,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Main orchestration entry point for Zentex learning.
    """
    trace_id = str(uuid.uuid4())
    turn_id = "cycle_" + trace_id[:8]
    meta = describe_direction(direction)

    if store is None:
        store = get_runtime_service().get_transcript_store()

    if store:
        store.write_entry(
        session_id=LEARNING_SESSION_ID,
        turn_id=turn_id,
        entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
        payload={
            "kind": "cycle_started",
            "direction": direction.value,
            "architecture_ref": meta["ref"],
            "dry_run": dry_run,
        },
        source="zentex.learning.engine",
        trace_id=trace_id,
    )

    if dry_run:
        if store:
            store.write_entry(
                session_id=LEARNING_SESSION_ID,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={"kind": "dry_run_ack"},
                source="zentex.learning.engine",
                trace_id=trace_id,
            )
        return LearningCycleResult(status="dry_run", trace_id=trace_id)

    if load_factor > 0.8:
        store.write_entry(
            session_id=LEARNING_SESSION_ID,
            turn_id=turn_id,
            entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
            payload={"kind": "aborted", "reason": "load_factor too high"},
            source="zentex.learning.engine",
            trace_id=trace_id,
        )
        return LearningCycleResult(status="budget_hold", trace_id=trace_id)

    if direction == LearningDirection.G16_TOOL_SELF_STUDY:
        from zentex.learning.g16_pipeline import run_g16_dynamic_tool_self_study

        doc_url = (extra_context or {}).get("doc_url")
        if not doc_url or not provider:
            store.write_entry(
                session_id=LEARNING_SESSION_ID,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={"kind": "aborted", "reason": "G16 requires 'doc_url' and 'provider'"},
                source="zentex.learning.engine",
                trace_id=trace_id,
            )
            return LearningCycleResult(status="aborted", trace_id=trace_id)

        record = await run_g16_dynamic_tool_self_study(
            doc_url=doc_url,
            provider=provider,
            store=store,
            trace_id=trace_id,
        )
        
        if record:
            store.write_entry(
                session_id=LEARNING_SESSION_ID,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={
                    "kind": "completed",
                    "direction": direction.value,
                    "tool_name": record.tool_name,
                    "summary": f"Self-study from {doc_url} successful.",
                },
                source="zentex.learning.engine",
                trace_id=trace_id,
            )
            return LearningCycleResult(
                status="completed",
                trace_id=trace_id,
                detail={"tool_name": record.tool_name}
            )
        else:
            store.write_entry(
                session_id=LEARNING_SESSION_ID,
                turn_id=turn_id,
                entry_type=BrainTranscriptEntryType.LEARNING_ENGINE_EVENT,
                payload={"kind": "aborted", "reason": "G16 pipeline returned no record (sandbox rejection or max attempts exhausted)"},
                source="zentex.learning.engine",
                trace_id=trace_id,
            )
            return LearningCycleResult(status="aborted", trace_id=trace_id)

    return LearningCycleResult(status="unknown_direction", trace_id=trace_id)


# ────────────────────────────────────────────────────────────────
#  通用对外方法 / Universal Public API
# ────────────────────────────────────────────────────────────────


async def start_learning(
    *,
    store: Optional[Any] = None,
    direction: str | LearningDirection,
    provider: Optional[ModelProviderSpec] = None,
    doc_url: Optional[str] = None,
    dry_run: bool = False,
    load_factor: float = 0.0,
) -> Any:
    """
    统一的学习启动入口。

    外部模块（Web API、Agent、CLI）通过此方法触发学习循环，
    无需直接构造 run_learning_cycle 的复杂参数。

    Args:
        store:        Transcript 存储实例。
        direction:    学习方向，可传字符串（如 "g16_tool_self_study"）或枚举。
        provider:     模型 Provider（G16 等方向必需）。
        doc_url:      文档 URL（G16 方向必需）。
        dry_run:      是否为模拟运行。
        load_factor:  当前系统负载因子（0.0 ~ 1.0）。

    Returns:
        LearningCycleResult 实例。
    """
    if isinstance(direction, str):
        try:
            direction = LearningDirection(direction)
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
        store = get_runtime_service().get_transcript_store()

    return await run_learning_cycle(
        store=store,
        direction=direction,
        provider=provider,
        dry_run=dry_run,
        load_factor=load_factor,
        extra_context=extra_context,
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
        store:    Transcript 存储实例。
        trace_id: 可选的追踪 ID，用于过滤特定学习周期。
        limit:    返回的最近事件数量上限。

    Returns:
        包含可用方向、最近事件等信息的字典。
    """
    if store is None:
        store = get_runtime_service().get_transcript_store()

    if not store:
        return {
            "available_directions": list_available_directions(),
            "recent_events_count": 0,
            "recent_events": [],
            "error": "Transcript store not available"
        }

    entries = store.read_by_session_id(LEARNING_SESSION_ID)
    if trace_id:
        entries = [e for e in entries if e.trace_id == trace_id]
    recent = sorted(entries, key=lambda e: e.created_at, reverse=True)[:limit]

    return {
        "available_directions": list_available_directions(),
        "recent_events_count": len(entries),
        "recent_events": [
            {
                "entry_id": e.entry_id,
                "trace_id": e.trace_id,
                "entry_type": e.entry_type.value,
                "payload": e.payload,
                "created_at": str(e.created_at),
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
#    │  G16 Tool Self-Study Pipeline         │
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
#    G16_TOOL_SELF_STUDY  — 基于文档的自主工具发现与验证
#    G24_CURIOSITY        — 好奇心驱动的探索性数据摄入（规划中）
#
# ════════════════════════════════════════════════════════════════════
