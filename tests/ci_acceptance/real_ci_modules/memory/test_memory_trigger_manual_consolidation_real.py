from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.kernel.state_domain.brain_transcript import BrainTranscriptStore
from zentex.memory.consolidation.consolidation import (
    ConsolidationEngine,
    ForgettableNoiseRule,
    ReflectionClusteringPlugin,
)
from zentex.web_console.router import api_router


def _build_real_consolidation_engine(tmp_path, suffix: str) -> ConsolidationEngine:
    transcript_store = BrainTranscriptStore(tmp_path / f"g59-transcript-{suffix}.sqlite3")
    return ConsolidationEngine(
        llm_service=None,
        analysis_plugins=[ReflectionClusteringPlugin()],
        transcript_store=transcript_store,
        brain_scope=f"g59-brain-{suffix}",
    )


def test_memory_trigger_manual_consolidation_real(real_ci_runtime) -> None:
    """功能：验证 memory service 可手动触发整理任务。"""
    handle = real_ci_runtime.memory_service.trigger_manual_consolidation(operator="ci")
    assert handle.cycle_id
    assert handle.lease_id

    engine = real_ci_runtime.memory_service.get_consolidation_engine()
    cycles = engine.list_cycles(cycle_id=handle.cycle_id)
    assert cycles, "manual consolidation 未进入 engine 周期列表"
    assert cycles[0].cycle_id == handle.cycle_id
    assert cycles[0].status in {"queued", "completed", "failed"}
    assert cycles[0].trigger_reason in {"manual", "manual_web_console"}


def test_g59_consolidation_engine_completes_cycle_preserves_refs_and_tombstones_real(tmp_path) -> None:
    suffix = unique_suffix()
    engine = _build_real_consolidation_engine(tmp_path, suffix)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=120)).timestamp()
    records = [
        {
            "ref_id": f"reflection-a-{suffix}",
            "kind": "reflection",
            "topic": "directory-role-failure",
            "risk_level": "medium",
            "outcome_type": "failure",
            "summary": "Role inference failed in a complex directory.",
            "reuse_value": 0.8,
            "confidence": 0.9,
            "created_at_ts": old_ts,
        },
        {
            "ref_id": f"reflection-b-{suffix}",
            "kind": "reflection",
            "topic": "directory-role-failure",
            "risk_level": "medium",
            "outcome_type": "failure",
            "summary": "A second real failure with the same role-inference pattern.",
            "reuse_value": 0.75,
            "confidence": 0.85,
            "created_at_ts": old_ts,
        },
        {
            "ref_id": f"reflection-c-{suffix}",
            "kind": "reflection",
            "topic": "directory-role-failure",
            "risk_level": "medium",
            "outcome_type": "failure",
            "summary": "A third matching failure makes the pattern stable enough to quarantine.",
            "reuse_value": 0.7,
            "confidence": 0.8,
            "created_at_ts": old_ts,
        },
        {
            "ref_id": f"noise-{suffix}",
            "kind": "low_value_reflection",
            "topic": "obsolete-reminder",
            "summary": "Single stale low-value note.",
            "reuse_value": 0.01,
            "confidence": 0.1,
            "created_at_ts": old_ts,
        },
        {
            "ref_id": f"identity_role_pack-{suffix}",
            "kind": "low_value_reflection",
            "topic": "identity",
            "summary": "Protected identity anchor must not be tombstoned.",
            "reuse_value": 0.0,
            "confidence": 0.0,
            "created_at_ts": old_ts,
        },
    ]
    engine.seed_memory_snapshot(
        ref_versions={item["ref_id"]: 0 for item in records},
        tombstone_state={item["ref_id"]: False for item in records},
        snapshot_version=0,
    )

    cycle = engine.run_cycle(
        trigger_reason="manual_real_test",
        input_memory_refs=records,
        noise_rules=[
            ForgettableNoiseRule(
                rule_id=f"low-value-{suffix}",
                noise_kind="low_value_reflection",
                age_threshold_seconds=30 * 24 * 3600,
                reuse_threshold=0.2,
                confidence_threshold=0.3,
            )
        ],
        context={"operator": "ci"},
        idempotency_key=f"g59-{suffix}",
    )

    assert cycle.status == "completed"
    assert cycle.trigger_reason == "manual_real_test"
    assert cycle.input_refs == [item["ref_id"] for item in records]
    assert set(cycle.compressed_refs) >= {
        f"reflection-a-{suffix}",
        f"reflection-b-{suffix}",
        f"reflection-c-{suffix}",
    }
    assert f"noise-{suffix}" in cycle.pruned_refs
    assert f"identity_role_pack-{suffix}" not in cycle.pruned_refs
    assert cycle.promotion_candidates
    assert any(candidate.status == "candidate" for candidate in cycle.promotion_candidates)
    assert cycle.summary.startswith("Deterministic B8 consolidation completed")

    queried = engine.list_cycles(cycle_id=cycle.cycle_id)
    assert len(queried) == 1
    assert queried[0].cycle_id == cycle.cycle_id
    assert queried[0].status == "completed"
    assert queried[0].pruned_refs == cycle.pruned_refs

    transcript_entries = engine._transcript_store.read_entries(
        session_id=f"memory:{engine.brain_scope}",
        turn_id=cycle.cycle_id,
    )
    assert transcript_entries
    assert transcript_entries[-1].entry_type.value == "consolidation_completed"
    assert transcript_entries[-1].payload["cycle_id"] == cycle.cycle_id


def test_g59_consolidation_api_requests_trigger_query_and_fail_closed_real(tmp_path) -> None:
    suffix = unique_suffix()
    engine = _build_real_consolidation_engine(tmp_path, suffix)
    app = FastAPI()
    app.include_router(api_router)
    app.state.consolidation_engine = engine

    with live_http_server(app) as base_url:
        trigger_response = requests.post(f"{base_url}/api/web/memory/consolidation/trigger", timeout=20)
        assert trigger_response.status_code == 200, trigger_response.text
        triggered = trigger_response.json()
        assert triggered["status"] == "triggered"
        assert triggered["cycle_id"]
        assert triggered["queued_cycle"]["cycle_id"] == triggered["cycle_id"]
        assert triggered["queued_cycle"]["status"] in {"queued", "completed"}

        cycles_payload = None
        for _ in range(50):
            query_response = requests.get(f"{base_url}/api/web/memory/consolidation-cycles", timeout=20)
            assert query_response.status_code == 200, query_response.text
            cycles_payload = query_response.json()
            queried = [
                cycle for cycle in cycles_payload["cycles"]
                if cycle["cycle_id"] == triggered["cycle_id"]
            ]
            if queried and queried[0]["status"] == "completed":
                break
            time.sleep(0.05)
        assert cycles_payload is not None
        queried = [cycle for cycle in cycles_payload["cycles"] if cycle["cycle_id"] == triggered["cycle_id"]]
        assert len(queried) == 1
        assert queried[0]["status"] == "completed"
        assert queried[0]["trigger_reason"] == "manual"
        assert queried[0]["summary"].startswith("Deterministic B8 consolidation completed")

    missing_app = FastAPI()
    missing_app.include_router(api_router)
    with live_http_server(missing_app) as base_url:
        failed = requests.post(f"{base_url}/api/web/memory/consolidation/trigger", timeout=20)
        assert failed.status_code == 503
        assert "Consolidation engine not available" in failed.text
