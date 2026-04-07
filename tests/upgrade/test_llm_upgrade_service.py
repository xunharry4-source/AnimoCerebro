from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.upgrade.llm.models import LLMUpgradeRequest  # noqa: E402
from zentex.upgrade.llm.service import DSPyLLMUpgradeService  # noqa: E402


def test_llm_upgrade_service_fails_closed_when_dspy_is_missing() -> None:
    service = DSPyLLMUpgradeService()
    request = LLMUpgradeRequest(
        program_id="reasoning-core",
        target_component="planner",
        baseline_version="1.2.3",
        target_metric="answer_accuracy",
        dataset_refs=["datasets/qa.jsonl"],
        objective_summary="Improve planner accuracy on hard cases.",
        validation_commands=["pytest tests/runtime/test_think_loop.py -q"],
    )

    with pytest.raises(RuntimeError, match="DSPy is not installed"):
        service.plan_candidate(request)
