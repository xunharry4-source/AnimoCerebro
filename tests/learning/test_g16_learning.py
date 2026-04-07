import pytest
from unittest.mock import MagicMock
from pathlib import Path

from zentex.core.model_provider_spec import ModelProviderSpec
from zentex.learning.directions import LearningDirection
from zentex.learning.engine import run_learning_cycle
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore
from zentex.learning.budget import ReasoningBudget

@pytest.mark.asyncio
async def test_g16_successful_registration(tmp_path: Path) -> None:
    """
    Verification of successful tool registration after sandbox pass.
    """
    store = BrainTranscriptStore(tmp_path / "t1.jsonl")
    budget = ReasoningBudget(remaining_tokens=10000)

    mock_provider = MagicMock(spec=ModelProviderSpec)
    mock_provider.generate_json.return_value = {
        "tool_name": "valid_tool",
        "description": "A valid identity tool",
        "usage_example": "identity(x)",
        "input_schema": {},
        "output_schema": {},
        "test_cases": [{"input": "hello", "expected": "hello"}]
    }

    out = await run_learning_cycle(
        store=store,
        direction=LearningDirection.G16_TOOL_SELF_STUDY,
        provider=mock_provider,
        budget=budget,
        extra_context={"doc_url": "http://example.com/doc"}
    )

    assert out["status"] == "completed"
    assert out["detail"]["tool_name"] == "valid_tool"
    
    entries = store.get_entries_snapshot()
    completed = [e for e in entries if e.payload.get("kind") == "completed"]
    assert len(completed) == 1
    assert "successful" in completed[0].payload["summary"]

@pytest.mark.asyncio
async def test_g16_sandbox_interception_on_invalid_candidate(tmp_path: Path) -> None:
    """
    Verification of sandbox blocking tool with mismatching test cases.
    """
    store = BrainTranscriptStore(tmp_path / "t2.jsonl")
    budget = ReasoningBudget(remaining_tokens=10000)

    mock_provider = MagicMock(spec=ModelProviderSpec)
    mock_provider.generate_json.return_value = {
        "tool_name": "bad_tool",
        "description": "A tool that fails validation",
        "usage_example": "fail(x)",
        "input_schema": {},
        "output_schema": {},
        "test_cases": [{"input": "hello", "expected": "world"}] # Sandbox logic uses identity, so this fails
    }

    out = await run_learning_cycle(
        store=store,
        direction=LearningDirection.G16_TOOL_SELF_STUDY,
        provider=mock_provider,
        budget=budget,
        extra_context={"doc_url": "http://example.com/doc"}
    )

    assert out["status"] == "aborted"
    
    entries = store.get_entries_snapshot()
    aborted = [e for e in entries if e.payload.get("kind") == "aborted"]
    assert len(aborted) == 1
    assert "Sandbox validation failed" in aborted[0].payload["reason"]
