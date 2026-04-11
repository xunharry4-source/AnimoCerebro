from __future__ import annotations

"""Public learning facade for cross-module access."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection, describe_direction
from zentex.learning.engine import (
    LEARNING_SESSION_ID,
    LearningCycleResult,
    get_learning_status,
    list_available_directions,
    run_learning_cycle,
    start_learning,
)


class LearningRecord(BaseModel):
    """Compatibility record for callers that need a typed learning event."""

    model_config = ConfigDict(extra="allow")

    trace_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    detail: Dict[str, Any] = Field(default_factory=dict)


class LearningOutcome(BaseModel):
    """Typed wrapper over the engine result payload."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    detail: Dict[str, Any] = Field(default_factory=dict)


class LearningServiceFacade:
    """Thin facade that delegates to the learning engine public API."""

    async def start_cycle(
        self,
        *,
        direction: str | LearningDirection,
        provider: Any = None,
        doc_url: str | None = None,
        dry_run: bool = False,
        load_factor: float = 0.0,
        store: Any = None,
    ) -> LearningOutcome:
        result = await start_learning(
            store=store,
            direction=direction,
            provider=provider,
            doc_url=doc_url,
            dry_run=dry_run,
            load_factor=load_factor,
        )
        return _to_learning_outcome(result)

    def get_status(
        self,
        store: Any = None,
        *,
        trace_id: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        return get_learning_status(store, trace_id=trace_id, limit=limit)

    def list_directions(self) -> list[Dict[str, Any]]:
        return list_available_directions()


_default_service: LearningServiceFacade | None = None


def get_learning_service() -> LearningServiceFacade:
    global _default_service
    if _default_service is None:
        _default_service = LearningServiceFacade()
    return _default_service


def _to_learning_outcome(result: Any) -> LearningOutcome:
    payload = dict(result) if isinstance(result, dict) else {
        "status": getattr(result, "status", "unknown"),
        "trace_id": getattr(result, "trace_id", ""),
        "detail": getattr(result, "detail", {}),
    }
    return LearningOutcome(
        status=str(payload.get("status") or "unknown"),
        trace_id=str(payload.get("trace_id") or ""),
        detail=dict(payload.get("detail") or {}),
    )


__all__ = [
    "LearningServiceFacade",
    "LearningRecord",
    "LearningOutcome",
    "LearningCycleResult",
    "ReasoningBudget",
    "LearningDirection",
    "describe_direction",
    "LEARNING_SESSION_ID",
    "run_learning_cycle",
    "start_learning",
    "list_available_directions",
    "get_learning_status",
    "get_learning_service",
]
