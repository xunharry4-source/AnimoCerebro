from __future__ import annotations

import copy
import json

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.continuity.soul_migration import (
    SnapshotExportRequest,
    SnapshotRestoreRequest,
    SoulMigrationManager,
)


PASSPHRASE = "g34-real-passphrase"


def _snapshot_payload() -> dict:
    return {
        "source_instance_id": "zentex-primary-a",
        "target_instance_id": "zentex-standby-b",
        "operator_id": "continuity-operator",
        "passphrase": PASSPHRASE,
        "identity_kernel": {
            "role": "Zentex Primary Auditor",
            "mission": "preserve continuity during migration",
            "core_values": ["auditability", "continuity", "human authorization"],
            "continuity_lock": {"locked_fields": ["role", "mission"], "enforced": True},
        },
        "memory_snapshot": [
            {
                "memory_id": "mem-g34-001",
                "tier": "hot",
                "summary": "remember deployment handoff checklist",
                "hash": "memhash001",
            },
            {
                "memory_id": "mem-g34-002",
                "tier": "warm",
                "summary": "prior takeover failed without authorization",
                "hash": "memhash002",
            },
        ],
        "goal_tree": {
            "goal_id": "goal-g34-root",
            "title": "complete migration without continuity drift",
            "children": [{"goal_id": "goal-g34-verify", "title": "verify restored memory hashes"}],
        },
        "audit_chain_refs": ["audit-g34-export", "audit-g34-restore"],
    }


def test_g34_direct_export_encrypts_plaintext_restores_exact_snapshot_and_blocks_tamper() -> None:
    manager = SoulMigrationManager()
    request = SnapshotExportRequest(**_snapshot_payload())
    package = manager.export_snapshot(request)
    package_text = json.dumps(package.model_dump(mode="json"), ensure_ascii=False)

    assert package.feature_code == "G34"
    assert package.encryption == "AESGCM-256"
    assert package.kdf == "PBKDF2HMAC-SHA256-200000"
    assert package.manifest["memory_record_count"] == 2
    assert package.manifest["goal_root_id"] == "goal-g34-root"
    assert package.signature.startswith("hmac-sha256=")
    assert "Zentex Primary Auditor" not in package_text
    assert "remember deployment handoff checklist" not in package_text

    restore = manager.restore_snapshot(
        SnapshotRestoreRequest(
            package=package,
            target_instance_id="zentex-standby-b",
            operator_id="restore-operator",
            passphrase=PASSPHRASE,
        )
    )
    queried_restore = manager.get_restore(restore.restore_id)
    queried_backup = manager.get_backup(package.package_id)

    assert restore.status == "restored"
    assert restore.continuity_check.allowed is True
    assert restore.continuity_check.signature_verified is True
    assert restore.continuity_check.integrity_verified is True
    assert restore.continuity_check.target_binding_verified is True
    assert restore.continuity_check.identity_fields_verified is True
    assert restore.continuity_check.memory_hash_verified is True
    assert restore.restored_snapshot is not None
    assert restore.restored_snapshot["identity_kernel"] == request.identity_kernel
    assert restore.restored_snapshot["memory_snapshot"] == request.memory_snapshot
    assert restore.restored_snapshot["goal_tree"] == request.goal_tree
    assert queried_restore.restore_id == restore.restore_id
    assert queried_backup.package_id == package.package_id

    tampered_package = package.model_copy(update={"ciphertext_b64": package.ciphertext_b64[:-4] + "AAAA"})
    with pytest.raises(ValueError, match="signature verification failed|decryption failed"):
        manager.restore_snapshot(
            SnapshotRestoreRequest(
                package=tampered_package,
                target_instance_id="zentex-standby-b",
                operator_id="restore-operator",
                passphrase=PASSPHRASE,
            )
        )

    assert [event.action for event in manager.list_audit_events()] == ["export", "restore"]


def test_g34_api_uses_requests_for_export_restore_takeover_and_read_after_write(
    acceptance_app: FastAPI,
) -> None:
    acceptance_app.state.soul_migration_manager = SoulMigrationManager()
    payload = _snapshot_payload()
    with live_http_server(acceptance_app) as base_url:
        export_response = requests.post(f"{base_url}/api/web/soul-migration/export", json=payload, timeout=10)
        assert export_response.status_code == 200
        package = export_response.json()["package"]
        package_id = package["package_id"]

        backup_response = requests.get(f"{base_url}/api/web/soul-migration/backups/{package_id}", timeout=10)
        wrong_target_response = requests.post(
            f"{base_url}/api/web/soul-migration/restore",
            json={
                "package": package,
                "target_instance_id": "zentex-wrong-target",
                "operator_id": "restore-operator",
                "passphrase": PASSPHRASE,
            },
            timeout=10,
        )
        restore_response = requests.post(
            f"{base_url}/api/web/soul-migration/restore",
            json={
                "package": package,
                "target_instance_id": "zentex-standby-b",
                "operator_id": "restore-operator",
                "passphrase": PASSPHRASE,
            },
            timeout=10,
        )
        assert restore_response.status_code == 200
        restore_payload = restore_response.json()["restore"]
        restore_id = restore_payload["restore_id"]
        restore_query = requests.get(f"{base_url}/api/web/soul-migration/restores/{restore_id}", timeout=10)

        requests.post(
            f"{base_url}/api/web/soul-migration/heartbeat",
            json={
                "instance_id": "zentex-primary-a",
                "role": "primary",
                "observed_at": "2026-04-29T00:00:00+08:00",
                "status": "online",
            },
            timeout=10,
        )
        standby_heartbeat = requests.post(
            f"{base_url}/api/web/soul-migration/heartbeat",
            json={
                "instance_id": "zentex-standby-b",
                "role": "standby",
                "observed_at": "2026-04-29T00:02:00+08:00",
                "status": "online",
            },
            timeout=10,
        )
        blocked_status = requests.get(
            f"{base_url}/api/web/soul-migration/takeover/status",
            params={
                "primary_instance_id": "zentex-primary-a",
                "standby_instance_id": "zentex-standby-b",
                "observed_at": "2026-04-29T00:02:00+08:00",
                "heartbeat_timeout_seconds": 30,
            },
            timeout=10,
        )
        authorization_response = requests.post(
            f"{base_url}/api/web/soul-migration/takeover/authorize",
            json={
                "primary_instance_id": "zentex-primary-a",
                "standby_instance_id": "zentex-standby-b",
                "operator_id": "human-supervisor",
                "reason": "primary heartbeat exceeded timeout during migration drill",
            },
            timeout=10,
        )
        ready_status = requests.get(
            f"{base_url}/api/web/soul-migration/takeover/status",
            params={
                "primary_instance_id": "zentex-primary-a",
                "standby_instance_id": "zentex-standby-b",
                "observed_at": "2026-04-29T00:02:00+08:00",
                "heartbeat_timeout_seconds": 30,
            },
            timeout=10,
        )
        token = ready_status.json()["takeover_token"]
        commit_response = requests.post(
            f"{base_url}/api/web/soul-migration/takeover/commit",
            json={
                "primary_instance_id": "zentex-primary-a",
                "standby_instance_id": "zentex-standby-b",
                "takeover_token": token,
                "operator_id": "human-supervisor",
                "observed_at": "2026-04-29T00:02:00+08:00",
                "heartbeat_timeout_seconds": 30,
            },
            timeout=10,
        )
        audit_response = requests.get(f"{base_url}/api/web/soul-migration/audit", timeout=10)

    package_text = json.dumps(package, ensure_ascii=False)
    assert backup_response.status_code == 200
    assert backup_response.json()["package_id"] == package_id
    assert "Zentex Primary Auditor" not in package_text
    assert "prior takeover failed without authorization" not in package_text
    assert package["manifest"]["memory_record_count"] == 2
    assert wrong_target_response.status_code == 400
    assert wrong_target_response.json()["detail"]["error"] == "restore_failed"
    assert "target binding" in wrong_target_response.json()["detail"]["message"]
    assert restore_payload["status"] == "restored"
    assert restore_payload["continuity_check"]["allowed"] is True
    assert restore_payload["restored_snapshot"]["identity_kernel"]["role"] == "Zentex Primary Auditor"
    assert restore_payload["restored_snapshot"]["memory_snapshot"][0]["memory_id"] == "mem-g34-001"
    assert restore_query.json()["restore_id"] == restore_id
    assert standby_heartbeat.status_code == 200
    assert standby_heartbeat.json()["heartbeat"]["instance_id"] == "zentex-standby-b"
    assert blocked_status.json()["status"] == "blocked"
    assert "takeover_authorization_missing" in blocked_status.json()["reasons"]
    assert authorization_response.status_code == 200
    assert ready_status.json()["status"] == "ready"
    assert ready_status.json()["heartbeat_age_seconds"] == 120.0
    assert ready_status.json()["manual_commit_required"] is True
    assert commit_response.status_code == 200
    assert commit_response.json()["takeover"]["status"] == "committed"
    assert commit_response.json()["takeover"]["manual_commit_required"] is False
    assert [event["action"] for event in audit_response.json()] == [
        "export",
        "restore",
        "heartbeat",
        "heartbeat",
        "takeover_authorized",
        "takeover_committed",
    ]


def test_g34_api_rejects_wrong_passphrase_without_restoring_state(acceptance_app: FastAPI) -> None:
    acceptance_app.state.soul_migration_manager = SoulMigrationManager()
    payload = _snapshot_payload()
    with live_http_server(acceptance_app) as base_url:
        export_response = requests.post(f"{base_url}/api/web/soul-migration/export", json=payload, timeout=10)
        package = export_response.json()["package"]
        wrong = copy.deepcopy(package)
        restore_response = requests.post(
            f"{base_url}/api/web/soul-migration/restore",
            json={
                "package": wrong,
                "target_instance_id": "zentex-standby-b",
                "operator_id": "restore-operator",
                "passphrase": "incorrect-passphrase",
            },
            timeout=10,
        )
        audit_response = requests.get(f"{base_url}/api/web/soul-migration/audit", timeout=10)

    assert restore_response.status_code == 400
    assert restore_response.json()["detail"]["error"] == "restore_failed"
    assert "signature verification failed" in restore_response.json()["detail"]["message"]
    assert [event["action"] for event in audit_response.json()] == ["export"]
