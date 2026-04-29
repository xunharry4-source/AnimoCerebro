from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.memory.management.enhanced import EnhancedMemoryRecord
from zentex.memory.memory_lifecycle_governance import MemoryLifecycleGovernance, MemoryLifecyclePolicy
from zentex.memory.service import MemoryService


UTC = timezone.utc


def _store_record(
    service: MemoryService,
    seed: str,
    *,
    created_at: datetime | None = None,
    pattern_key: str | None = None,
    confidence_score: float = 0.75,
    lifecycle_value: str | None = None,
    content_suffix: str = "",
) -> EnhancedMemoryRecord:
    payload = {}
    if pattern_key:
        payload["pattern_key"] = pattern_key
    if lifecycle_value:
        payload["lifecycle_value"] = lifecycle_value
    record = EnhancedMemoryRecord(
        memory_layer="semantic",
        source_kind="operator",
        title=f"lifecycle memory {seed}",
        summary=f"lifecycle summary {seed}",
        content=f"lifecycle durable recall content {seed} {content_suffix}".strip(),
        trace_id=f"trace-lifecycle-{seed}",
        tags=["memory-lifecycle", f"pattern:{pattern_key}"] if pattern_key else ["memory-lifecycle"],
        payload=payload,
        created_at=created_at or datetime.now(UTC),
        confidence_score=confidence_score,
        verification_status="verified",
    )
    return service._internal_service._append_semantic(record)


def _governance(service: MemoryService, *, hot_budget_bytes: int = 10_000_000) -> MemoryLifecycleGovernance:
    return MemoryLifecycleGovernance(
        service._internal_service,
        policy=MemoryLifecyclePolicy(hot_budget_bytes=hot_budget_bytes),
    )


def test_memory_lifecycle_direct_cycle_compaction_rewarm_and_contamination_affect_recall(tmp_path) -> None:
    seed = unique_suffix()
    now = datetime.now(UTC)
    service = MemoryService(storage_root=tmp_path / "direct")
    governance = _governance(service)
    pattern = f"pattern-{seed}"
    hot_records = [
        _store_record(service, f"{seed}-hot-{idx}", pattern_key=pattern, created_at=now - timedelta(days=idx))
        for idx in range(3)
    ]
    old_records = [
        _store_record(service, f"{seed}-old-{idx}", pattern_key=pattern, created_at=now - timedelta(days=30 + idx))
        for idx in range(2)
    ]
    low_value = _store_record(
        service,
        f"{seed}-low",
        created_at=now - timedelta(days=1),
        confidence_score=0.1,
        lifecycle_value="low",
        content_suffix="low value must disappear from governed recall",
    )

    report = governance.run_cycle(operator="ci-lifecycle", now=now)

    assert report.scanned_count == 6
    assert low_value.memory_id in report.archived_memory_ids
    assert {candidate.candidate_type for candidate in report.promotion_candidates} == {"experience", "strategy_patch"}
    strategy = [candidate for candidate in report.promotion_candidates if candidate.candidate_type == "strategy_patch"][0]
    assert strategy.occurrence_count == 5
    assert strategy.window_count >= 2
    low_managed = service.get_record(low_value.memory_id)
    assert low_managed is not None
    assert low_managed.status == "archived"
    assert low_managed.visibility == "hidden"
    assert low_value.memory_id not in {
        row.hit.memory_id for row in governance.governed_recall("low value must disappear", limit=20)
    }
    old_state = {state.memory_id: state.lifecycle_tier for state in governance.list_states()}
    assert old_state[old_records[0].memory_id] == "warm"

    before_compact_hits = governance.governed_recall(seed, limit=10)
    assert {row.hit.memory_id for row in before_compact_hits} >= {hot_records[0].memory_id, old_records[0].memory_id}
    compaction = governance.compress_memories(
        [hot_records[0].memory_id, hot_records[1].memory_id],
        summary=f"compressed lifecycle summary {seed}",
        operator="ci-lifecycle",
    )
    assert compaction.records_before == 2
    assert compaction.records_after == 1
    assert compaction.reference_chain_preserved is True
    assert compaction.benefit_ratio > 0
    first_source = service.get_record(hot_records[0].memory_id)
    assert first_source is not None
    assert first_source.status == "archived"
    assert first_source.visibility == "hidden"
    assert first_source.superseded_by_memory_id == compaction.compressed_memory_id
    assert hot_records[0].memory_id not in {row.hit.memory_id for row in governance.governed_recall(seed, limit=20)}

    restored = governance.restore_compressed_chain(compaction.compressed_memory_id, operator="ci-restore")
    assert {state.memory_id for state in restored} == {hot_records[0].memory_id, hot_records[1].memory_id}
    restored_managed = service.get_record(hot_records[0].memory_id)
    assert restored_managed is not None
    assert restored_managed.status == "active"
    assert restored_managed.visibility == "internal"
    assert hot_records[0].memory_id in {row.hit.memory_id for row in governance.governed_recall(seed, limit=20)}

    contaminated = governance.mark_contaminated(
        hot_records[0].memory_id,
        reason="ci contamination cannot rewarm",
        operator="ci-contaminate",
    )
    assert contaminated.rewarm_blocked is True
    assert service.get_record(hot_records[0].memory_id).status == "rejected"
    assert hot_records[0].memory_id not in {row.hit.memory_id for row in governance.governed_recall(seed, limit=20)}
    with pytest.raises(ValueError, match="blocked from rewarm"):
        governance.rewarm_memory(hot_records[0].memory_id, operator="ci", reason="must fail")


def test_memory_lifecycle_service_methods_are_real_delegates(tmp_path) -> None:
    seed = unique_suffix()
    service = MemoryService(storage_root=tmp_path / "service")
    record_a = _store_record(service, f"{seed}-a")
    record_b = _store_record(service, f"{seed}-b")

    assert service.get_memory_lifecycle_governance() is service.get_memory_lifecycle_governance()
    cycle = service.run_memory_lifecycle_cycle(operator="ci-service")
    assert cycle.scanned_count == 2
    assert service.list_memory_lifecycle_cycles()[0].cycle_id == cycle.cycle_id
    assert {row.hit.memory_id for row in service.recall_memory_lifecycle(seed, limit=10)} == {
        record_a.memory_id,
        record_b.memory_id,
    }

    compaction = service.compress_lifecycle_memories(
        [record_a.memory_id, record_b.memory_id],
        summary=f"service compaction {seed}",
        operator="ci-service",
    )
    assert service.list_memory_lifecycle_compactions()[0].report_id == compaction.report_id
    assert service.recall_memory_lifecycle(f"service compaction {seed}", limit=10)[0].hit.memory_id == compaction.compressed_memory_id
    restored = service.restore_lifecycle_compressed_chain(compaction.compressed_memory_id, operator="ci-service")
    assert {state.memory_id for state in restored} == {record_a.memory_id, record_b.memory_id}
    rewarm = service.rewarm_lifecycle_memory(record_a.memory_id, operator="ci-service", reason="explicit rewarm")
    assert rewarm.lifecycle_tier == "hot"
    contaminated = service.mark_lifecycle_memory_contaminated(
        record_a.memory_id,
        reason="service contamination",
        operator="ci-service",
    )
    assert contaminated.status == "rejected"
    assert record_a.memory_id not in {row.hit.memory_id for row in service.recall_memory_lifecycle(seed, limit=10)}
    assert service.list_memory_lifecycle_states()


def test_memory_lifecycle_api_uses_requests_and_checks_queries_after_each_write(
    acceptance_app: FastAPI,
    tmp_path,
) -> None:
    seed = unique_suffix()
    service = MemoryService(storage_root=tmp_path / "api")
    acceptance_app.state.memory_service = service
    record_a = _store_record(service, f"{seed}-api-a")
    record_b = _store_record(service, f"{seed}-api-b")
    old_record = _store_record(service, f"{seed}-api-old", created_at=datetime.now(UTC) - timedelta(days=30))

    with live_http_server(acceptance_app) as base_url:
        cycle_response = requests.post(
            f"{base_url}/api/web/memory-lifecycle/g39/cycles",
            json={"operator": "api-ci", "now": datetime.now(UTC).isoformat()},
            timeout=10,
        )
        assert cycle_response.status_code == 200, cycle_response.text
        assert cycle_response.json()["scanned_count"] == 3
        cycles_query = requests.get(f"{base_url}/api/web/memory-lifecycle/g39/cycles", timeout=10)
        assert cycles_query.status_code == 200
        assert cycles_query.json()[0]["cycle_id"] == cycle_response.json()["cycle_id"]

        recall_before = requests.get(
            f"{base_url}/api/web/memory-lifecycle/g39/recall",
            params={"query": seed, "limit": 10},
            timeout=10,
        )
        assert recall_before.status_code == 200, recall_before.text
        before_ids = {row["hit"]["memory_id"] for row in recall_before.json()}
        assert {record_a.memory_id, record_b.memory_id, old_record.memory_id} <= before_ids

        compaction_response = requests.post(
            f"{base_url}/api/web/memory-lifecycle/g39/compactions",
            json={
                "memory_ids": [record_a.memory_id, record_b.memory_id],
                "summary": f"api compaction summary {seed}",
                "operator": "api-ci",
            },
            timeout=10,
        )
        assert compaction_response.status_code == 200, compaction_response.text
        compressed_id = compaction_response.json()["compressed_memory_id"]
        compaction_query = requests.get(f"{base_url}/api/web/memory-lifecycle/g39/compactions", timeout=10)
        assert compaction_query.json()[0]["compressed_memory_id"] == compressed_id
        recall_after_compaction = requests.get(
            f"{base_url}/api/web/memory-lifecycle/g39/recall",
            params={"query": f"api compaction summary {seed}", "limit": 10},
            timeout=10,
        ).json()
        after_compaction_ids = {row["hit"]["memory_id"] for row in recall_after_compaction}
        assert record_a.memory_id not in after_compaction_ids
        assert record_b.memory_id not in after_compaction_ids
        assert compressed_id in after_compaction_ids

        restore_response = requests.post(
            f"{base_url}/api/web/memory-lifecycle/g39/compactions/{compressed_id}/restore",
            timeout=10,
        )
        assert restore_response.status_code == 200, restore_response.text
        assert {row["memory_id"] for row in restore_response.json()} == {record_a.memory_id, record_b.memory_id}
        recall_after_restore = requests.get(
            f"{base_url}/api/web/memory-lifecycle/g39/recall",
            params={"query": seed, "limit": 10},
            timeout=10,
        ).json()
        assert record_a.memory_id in {row["hit"]["memory_id"] for row in recall_after_restore}

        contaminate_response = requests.post(
            f"{base_url}/api/web/memory-lifecycle/g39/memories/{record_a.memory_id}/contamination",
            json={"reason": "api contamination", "operator": "api-ci"},
            timeout=10,
        )
        assert contaminate_response.status_code == 200, contaminate_response.text
        assert contaminate_response.json()["rewarm_blocked"] is True
        blocked_rewarm = requests.post(
            f"{base_url}/api/web/memory-lifecycle/g39/memories/{record_a.memory_id}/rewarm",
            json={"reason": "must stay blocked", "operator": "api-ci"},
            timeout=10,
        )
        assert blocked_rewarm.status_code == 409
        final_recall = requests.get(
            f"{base_url}/api/web/memory-lifecycle/g39/recall",
            params={"query": seed, "limit": 10},
            timeout=10,
        ).json()
        assert record_a.memory_id not in {row["hit"]["memory_id"] for row in final_recall}
        states = requests.get(f"{base_url}/api/web/memory-lifecycle/g39/states", timeout=10).json()
        state_by_id = {row["memory_id"]: row for row in states}
        assert state_by_id[record_a.memory_id]["status"] == "rejected"
        assert state_by_id[record_a.memory_id]["rewarm_blocked"] is True
