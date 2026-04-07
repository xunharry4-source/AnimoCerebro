from __future__ import annotations

from pathlib import Path

from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection
from zentex.learning.engine import LEARNING_SESSION_ID, run_learning_cycle
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore


import pytest

@pytest.mark.asyncio
async def test_dry_run_appends_transcript_without_provider(tmp_path: Path) -> None:
    store = BrainTranscriptStore(tmp_path / "t.jsonl")
    budget = ReasoningBudget(remaining_tokens=10000)
    out = await run_learning_cycle(
        store=store,
        direction=LearningDirection.G24_CURIOSITY,
        provider=None,
        budget=budget,
        dry_run=True,
    )
    assert out.status == "dry_run"
    entries = store.get_entries_snapshot()
    assert len(entries) == 2
    assert all(e.session_id == LEARNING_SESSION_ID for e in entries)
    assert all(e.entry_type == BrainTranscriptEntryType.LEARNING_ENGINE_EVENT for e in entries)
    kinds = [e.payload["kind"] for e in entries if isinstance(e.payload, dict)]  # type: ignore[index]
    assert kinds[0] == "cycle_started"
    assert kinds[1] == "dry_run_ack"


@pytest.mark.asyncio
async def test_aborts_when_provider_missing_and_not_dry_run(tmp_path: Path) -> None:
    store = BrainTranscriptStore(tmp_path / "t2.jsonl")
    budget = ReasoningBudget(remaining_tokens=10000)
    out = await run_learning_cycle(
        store=store,
        direction=LearningDirection.G16_TOOL_SELF_STUDY,
        provider=None,
        budget=budget,
        dry_run=False,
    )
    assert out.status == "aborted"
    kinds = [e.payload.get("kind") for e in store.get_entries_snapshot() if isinstance(e.payload, dict)]
    assert "aborted" in kinds


@pytest.mark.asyncio
async def test_budget_hold_on_high_load(tmp_path: Path) -> None:
    store = BrainTranscriptStore(tmp_path / "t3.jsonl")
    budget = ReasoningBudget(remaining_tokens=10000)
    out = await run_learning_cycle(
        store=store,
        direction=LearningDirection.G24_CURIOSITY,
        provider=None,
        budget=budget,
        load_factor=0.9,
        dry_run=False,
    )
    assert out.status == "budget_hold"
