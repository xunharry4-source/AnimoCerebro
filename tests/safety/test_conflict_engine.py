from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.safety.conflict_engine import (  # noqa: E402
    CognitiveConflictEngine,
    CognitiveConflictReport,
    ReconciliationPlan,
    StaleWriteError,
)


def test_reconciliation_plan_rejects_stale_snapshot_version() -> None:
    engine = CognitiveConflictEngine(brain_scope="cluster-a")
    report = CognitiveConflictReport(
        conflict_type="budget_conflict",
        severity="critical",
        suggested_resolution="pause_expansion",
        source_plugin_id="budget-conflict",
    )
    engine.ingest_reports([report])
    current_plan = engine.build_reconciliation_plan([report.conflict_id])
    engine.apply_reconciliation_plan(current_plan)

    stale_plan = ReconciliationPlan(
        conflict_ids=[report.conflict_id],
        resolution_actions=["pause_expansion"],
        brain_scope="cluster-a",
        snapshot_version=0,
    )

    with pytest.raises(StaleWriteError, match="Stale reconciliation plan"):
        engine.apply_reconciliation_plan(stale_plan)
