from __future__ import annotations

import json
from uuid import uuid4

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix


def test_memory_governance_snapshot_persistence_real(real_ci_runtime) -> None:
    """功能：真实 consolidation cycle 提交后，governance snapshot 必须实际落盘。"""
    suffix = unique_suffix()
    memory_record = real_ci_runtime.memory_service.remember(
        title=f"governance-snapshot-{suffix}",
        content=f"governance snapshot memory content {suffix}",
        summary=f"governance snapshot summary {suffix}",
        source="tests",
        tags=["governance-snapshot", suffix],
    )

    engine = real_ci_runtime.memory_service.get_consolidation_engine()
    snapshot_path = engine.get_governance_snapshot_path()
    before_exists = snapshot_path.exists()

    _handle, future = engine.submit_cycle(
        trigger_stage="sleep_phase",
        input_memory_refs=[
            {
                "ref_id": memory_record.memory_id,
                "title": memory_record.title,
                "summary": memory_record.summary,
                "reuse_value": 0.8,
                "created_at_ts": memory_record.created_at.timestamp(),
                "tags": list(memory_record.tags or []),
                "outcome_type": "success",
            }
        ],
        noise_rules=[],
        context={"operator": "ci", "reason": "snapshot_persistence"},
        idempotency_key=f"snapshot-{uuid4().hex}",
        snapshot_version=engine.snapshot_version,
    )
    cycle = future.result(timeout=30)

    assert cycle.status == "completed"
    assert snapshot_path.exists(), "expected governance snapshot file to be persisted"

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload.get("brain_scope") == engine.brain_scope
    assert int(payload.get("snapshot_version")) == cycle.snapshot_version
    assert isinstance(payload.get("memory_versions"), dict)
    assert isinstance(payload.get("tombstone_state"), dict)
    assert before_exists or snapshot_path.name.endswith(".json")
