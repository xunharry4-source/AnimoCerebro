from __future__ import annotations

import uuid
from typing import Any, Dict, Optional
from typing_extensions import Self

from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection, describe_direction
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore

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
    store: BrainTranscriptStore,
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
            return LearningCycleResult(status="aborted", trace_id=trace_id)

    return LearningCycleResult(status="unknown_direction", trace_id=trace_id)
