from __future__ import annotations

from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.memory.self_maintenance import (
    MemoryKeyStore,
    MemorySelfMaintenanceRuntime,
    MemorySelfMaintenanceStore,
)


def _install_runtime(acceptance_app: FastAPI, tmp_path) -> None:
    acceptance_app.state.memory_self_maintenance_runtime = MemorySelfMaintenanceRuntime(
        store=MemorySelfMaintenanceStore(tmp_path / "memory_self_maintenance.sqlite3"),
        key_store=MemoryKeyStore(tmp_path / "memory_keystore.json"),
    )


def test_memory_self_maintenance_compacts_encrypts_queries_and_rotates_real_requests(
    acceptance_app: FastAPI,
    tmp_path,
) -> None:
    _install_runtime(acceptance_app, tmp_path)
    suffix = uuid4().hex
    before_audit_count = len(acceptance_app.state.transcript_store.entries)
    secret_payload = {
        "identity": "core-anchor",
        "secret": f"identity-secret-{suffix}",
        "strategy": "never store plaintext sensitive memory",
    }
    patch_payload = {
        "patch_id": f"strategy-patch-{suffix}",
        "body": "prefer verified recall before execution",
    }

    request_payload = {
        "trigger_reason": "manual",
        "storage_used_bytes": 12000,
        "storage_budget_bytes": 10000,
        "reflection_records": [
            {
                "record_id": f"reflection-a-{suffix}",
                "topic": "api-audit",
                "risk_level": "high",
                "outcome_type": "blocked",
                "summary": "Provider failure must be explicit",
            },
            {
                "record_id": f"reflection-b-{suffix}",
                "topic": "api-audit",
                "risk_level": "high",
                "outcome_type": "blocked",
                "summary": "Do not hide audit errors",
            },
            {
                "record_id": f"reflection-c-{suffix}",
                "topic": "single",
                "risk_level": "low",
                "outcome_type": "ok",
                "summary": "Single record should not merge",
            },
        ],
        "experience_records": [
            {
                "record_id": f"experience-keep-{suffix}",
                "topic_hash": "topic-risk-policy",
                "risk_level": "high",
                "outcome_type": "blocked",
                "trust_level": 0.92,
                "repro_count": 3,
                "content": "kept record",
            },
            {
                "record_id": f"experience-superseded-{suffix}",
                "topic_hash": "topic-risk-policy",
                "risk_level": "high",
                "outcome_type": "blocked",
                "trust_level": 0.91,
                "repro_count": 10,
                "content": "superseded record",
            },
        ],
        "agenda_items": [
            {
                "item_id": f"agenda-expired-{suffix}",
                "summary": "old low risk hypothesis",
                "expires_at": "2026-01-01T00:00:00+00:00",
                "deferred_risk_score": 0.1,
                "active": True,
            },
            {
                "item_id": f"agenda-retained-{suffix}",
                "summary": "old but high risk hypothesis",
                "expires_at": "2026-01-01T00:00:00+00:00",
                "deferred_risk_score": 0.9,
                "active": True,
            },
        ],
        "noise_candidates": [
            {
                "memory_id": f"noise-tombstone-{suffix}",
                "summary": "stale low-value note",
                "tier": "warm",
                "last_hit_at": "2025-01-01T00:00:00+00:00",
                "repro_count": 0,
                "impact_score": 0.05,
            },
            {
                "memory_id": f"noise-retained-{suffix}",
                "summary": "stale but high impact note",
                "tier": "warm",
                "last_hit_at": "2025-01-01T00:00:00+00:00",
                "repro_count": 0,
                "impact_score": 0.85,
            },
        ],
        "sensitive_records": [
            {
                "record_id": f"identity-anchor-{suffix}",
                "record_type": "IdentityAnchor",
                "payload": secret_payload,
                "sensitivity": "secret",
            },
            {
                "record_id": f"strategy-patch-{suffix}",
                "record_type": "StrategyPatch",
                "payload": patch_payload,
                "sensitivity": "sensitive",
            },
        ],
        "now": "2026-04-29T12:00:00+00:00",
    }

    with live_http_server(acceptance_app) as base_url:
        run = requests.post(f"{base_url}/api/web/memory-self-maintenance/runs", json=request_payload, timeout=10)
        assert run.status_code == 200, run.text
        report = run.json()
        assert report["status"] == "completed"
        assert report["records_merged"] == 2
        assert report["records_deduped"] == 1
        assert report["records_cleaned"] == 2
        assert report["encrypted_records"] == 2
        assert report["errors"] == []
        assert report["storage_before_bytes"] == 12000
        assert report["storage_after_bytes"] < report["storage_before_bytes"]
        assert report["compression_ratio"] > 1
        assert report["experience_candidates"][0]["source_record_ids"] == [
            f"reflection-a-{suffix}",
            f"reflection-b-{suffix}",
        ]
        assert report["experience_candidates"][0]["reference_chain_preserved"] is True
        assert report["dedup_decisions"][0]["kept_record_id"] == f"experience-keep-{suffix}"
        assert report["dedup_decisions"][0]["superseded_record_ids"] == [f"experience-superseded-{suffix}"]
        assert report["expired_items"] == [
            {
                "item_id": f"agenda-expired-{suffix}",
                "action": "expired",
                "reason": "expired at 2026-01-01T00:00:00+00:00 with deferred_risk_score=0.1",
            }
        ]
        assert report["tombstones"][0]["memory_id"] == f"noise-tombstone-{suffix}"
        assert f"identity-anchor-{suffix}" in report["encrypted_record_ids"]

        reports = requests.get(f"{base_url}/api/web/memory-self-maintenance/reports", timeout=10)
        assert reports.status_code == 200
        assert [item["task_id"] for item in reports.json()] == [report["task_id"]]

        encrypted_list = requests.get(f"{base_url}/api/web/memory-self-maintenance/encrypted-records", timeout=10)
        assert encrypted_list.status_code == 200
        encrypted_items = encrypted_list.json()
        assert {item["record_id"] for item in encrypted_items} == {
            f"identity-anchor-{suffix}",
            f"strategy-patch-{suffix}",
        }
        assert all("payload" not in item and "ciphertext" not in item for item in encrypted_items)
        old_key_ids = {item["key_id"] for item in encrypted_items}
        assert len(old_key_ids) == 1

        raw = requests.get(
            f"{base_url}/api/web/memory-self-maintenance/raw-encrypted-records/identity-anchor-{suffix}",
            timeout=10,
        )
        assert raw.status_code == 200
        raw_payload = raw.json()
        assert raw_payload["ciphertext"]
        assert secret_payload["secret"] not in raw_payload["ciphertext"]
        assert "identity-secret" not in str(raw_payload)

        decrypted = requests.get(
            f"{base_url}/api/web/memory-self-maintenance/encrypted-records/identity-anchor-{suffix}",
            timeout=10,
        )
        assert decrypted.status_code == 200
        assert decrypted.json()["payload"] == secret_payload

        deletion_audit = requests.get(f"{base_url}/api/web/memory-self-maintenance/deletion-audit", timeout=10)
        assert deletion_audit.status_code == 200
        assert deletion_audit.json()[0]["memory_id"] == f"noise-tombstone-{suffix}"
        assert deletion_audit.json()[0]["deletion_kind"] == "tombstone"

        keys = requests.get(f"{base_url}/api/web/memory-self-maintenance/keys", timeout=10)
        assert keys.status_code == 200
        assert len(keys.json()) == 1
        assert "key_b64" not in keys.text
        assert keys.json()[0]["status"] == "active"

        rotation = requests.post(
            f"{base_url}/api/web/memory-self-maintenance/keys/rotate",
            json={"reencrypt_existing": True},
            timeout=10,
        )
        assert rotation.status_code == 200
        rotation_payload = rotation.json()
        assert rotation_payload["reencrypted_records"] == 2
        assert rotation_payload["revoked_old_key"] is True
        assert rotation_payload["old_key_id"] in old_key_ids
        assert rotation_payload["new_key_id"] not in old_key_ids

        after_rotation = requests.get(f"{base_url}/api/web/memory-self-maintenance/encrypted-records", timeout=10)
        assert after_rotation.status_code == 200
        assert {item["key_id"] for item in after_rotation.json()} == {rotation_payload["new_key_id"]}

        decrypted_after_rotation = requests.get(
            f"{base_url}/api/web/memory-self-maintenance/encrypted-records/identity-anchor-{suffix}",
            timeout=10,
        )
        assert decrypted_after_rotation.status_code == 200
        assert decrypted_after_rotation.json()["payload"] == secret_payload

    new_audits = acceptance_app.state.transcript_store.entries[before_audit_count:]
    assert len(new_audits) == 1
    audit_payload = new_audits[0]["payload"]
    assert audit_payload["event_type"] == "memory_self_maintenance_completed"
    assert audit_payload["records_merged"] == 2
    assert audit_payload["records_deduped"] == 1
    assert audit_payload["records_cleaned"] == 2
    assert audit_payload["encrypted_records"] == 2


def test_memory_self_maintenance_rejects_invalid_triggers_and_plaintext_fallback_real_requests(
    acceptance_app: FastAPI,
    tmp_path,
) -> None:
    _install_runtime(acceptance_app, tmp_path)
    suffix = uuid4().hex

    with live_http_server(acceptance_app) as base_url:
        high_load = requests.post(
            f"{base_url}/api/web/memory-self-maintenance/runs",
            json={
                "trigger_reason": "low_load",
                "load_average": 0.9,
                "low_load_threshold": 0.2,
                "storage_used_bytes": 100,
                "storage_budget_bytes": 1000,
                "now": "2026-04-29T12:00:00+00:00",
            },
            timeout=10,
        )
        assert high_load.status_code == 409
        assert "above threshold" in high_load.json()["detail"]

        unsupported_sensitive = requests.post(
            f"{base_url}/api/web/memory-self-maintenance/runs",
            json={
                "trigger_reason": "manual",
                "storage_used_bytes": 100,
                "storage_budget_bytes": 1000,
                "sensitive_records": [
                    {
                        "record_id": f"public-record-{suffix}",
                        "record_type": "IdentityAnchor",
                        "payload": {"secret": "should not be stored as plaintext"},
                        "sensitivity": "public",
                    }
                ],
                "now": "2026-04-29T12:00:00+00:00",
            },
            timeout=10,
        )
        assert unsupported_sensitive.status_code == 409
        assert "only sensitive or secret records" in unsupported_sensitive.json()["detail"]

        reports = requests.get(f"{base_url}/api/web/memory-self-maintenance/reports", timeout=10)
        assert reports.status_code == 200
        assert reports.json() == []

        encrypted = requests.get(f"{base_url}/api/web/memory-self-maintenance/encrypted-records", timeout=10)
        assert encrypted.status_code == 200
        assert encrypted.json() == []


def test_memory_compaction_scheduler_evaluates_runs_due_and_reports_real_requests(
    acceptance_app: FastAPI,
    tmp_path,
) -> None:
    _install_runtime(acceptance_app, tmp_path)
    suffix = uuid4().hex
    scheduled_payload = {
        "trigger_reason": "storage_over_budget",
        "load_average": 0.6,
        "low_load_threshold": 0.2,
        "storage_used_bytes": 5000,
        "storage_budget_bytes": 1000,
        "reflection_records": [
            {
                "record_id": f"scheduler-reflection-a-{suffix}",
                "topic": "scheduler",
                "risk_level": "medium",
                "outcome_type": "ok",
                "summary": "first scheduled reflection",
            },
            {
                "record_id": f"scheduler-reflection-b-{suffix}",
                "topic": "scheduler",
                "risk_level": "medium",
                "outcome_type": "ok",
                "summary": "second scheduled reflection",
            },
        ],
        "now": "2026-04-29T12:00:00+00:00",
    }

    with live_http_server(acceptance_app) as base_url:
        evaluation = requests.post(
            f"{base_url}/api/web/memory-self-maintenance/scheduler/evaluate",
            json=scheduled_payload,
            timeout=10,
        )
        assert evaluation.status_code == 200, evaluation.text
        decision = evaluation.json()
        assert decision["due"] is True
        assert decision["trigger_reason"] == "storage_over_budget"
        assert "storage_used_bytes_above_budget" in decision["reasons"]

        run_due = requests.post(
            f"{base_url}/api/web/memory-self-maintenance/scheduler/run-due",
            json=scheduled_payload,
            timeout=10,
        )
        assert run_due.status_code == 200, run_due.text
        payload = run_due.json()
        assert payload["decision"]["due"] is True
        assert payload["report"]["trigger_reason"] == "storage_over_budget"
        assert payload["report"]["records_merged"] == 2
        assert payload["report"]["storage_before_bytes"] == 5000
        assert payload["report"]["storage_after_bytes"] < 5000

        reports = requests.get(f"{base_url}/api/web/memory-self-maintenance/reports", timeout=10)
        assert reports.status_code == 200
        assert [item["task_id"] for item in reports.json()] == [payload["report"]["task_id"]]

        not_due = requests.post(
            f"{base_url}/api/web/memory-self-maintenance/scheduler/run-due",
            json={
                **scheduled_payload,
                "trigger_reason": "storage_over_budget",
                "storage_used_bytes": 500,
                "storage_budget_bytes": 1000,
            },
            timeout=10,
        )
        assert not_due.status_code == 200
        assert not_due.json()["decision"]["due"] is False
        assert not_due.json()["report"] is None
