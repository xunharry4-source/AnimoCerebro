from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.upgrade.llm.models import LLMUpgradeCandidate, LLMUpgradeExecutionPlan  # noqa: E402
from zentex.upgrade.llm.runtime import LLMUpgradeRuntime  # noqa: E402


def _candidate() -> LLMUpgradeCandidate:
    return LLMUpgradeCandidate(
        program_id="reasoning-core",
        target_component="planner",
        baseline_version="1.2.3",
        candidate_version="1.3.0-candidate",
        objective_summary="Improve planner accuracy on hard cases.",
        execution_plan=LLMUpgradeExecutionPlan(
            optimizer_name="mipro_v2",
            target_metric="answer_accuracy",
            dataset_refs=["datasets/qa.jsonl"],
            validation_commands=["pytest tests/runtime/test_think_loop.py -q"],
            required_artifacts=["optimizer_report.json"],
        ),
        release_gate=["Validation commands must pass."],
    )


def test_llm_upgrade_runtime_fails_closed_without_real_runner() -> None:
    runtime = LLMUpgradeRuntime()

    with pytest.raises(RuntimeError, match="real optimizer runner"):
        runtime.execute_candidate(_candidate())


def test_llm_upgrade_runtime_delegates_to_real_runner() -> None:
    runtime = LLMUpgradeRuntime(
        optimizer_runner=lambda candidate: {
            "candidate_version": candidate.candidate_version,
            "optimizer": candidate.execution_plan.optimizer_name,
            "status": "executed",
        }
    )

    result = runtime.execute_candidate(_candidate())

    assert result["candidate_version"] == "1.3.0-candidate"
    assert result["optimizer"] == "mipro_v2"
    assert result["status"] == "executed"
