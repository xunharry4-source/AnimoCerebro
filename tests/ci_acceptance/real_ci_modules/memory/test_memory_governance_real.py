from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.memory.memory_governance import (
    MemoryGovernance,
    MemoryRejectedError,
    MemoryTrustLevel,
)
from zentex.memory.management.enhanced import EnhancedMemoryRecord
from zentex.memory.service import MemoryService


UTC = timezone.utc


def _chain(seed: str) -> dict[str, list[str]]:
    return {
        "runtime_memory": [f"runtime-{seed}"],
        "goal": [f"goal-{seed}"],
        "action": [f"action-{seed}"],
        "execution": [f"execution-{seed}"],
        "reflection": [f"reflection-{seed}"],
    }


def _memory(seed: str, **overrides: object) -> EnhancedMemoryRecord:
    data = {
        "memory_layer": "semantic",
        "source_kind": "operator",
        "title": f"governed memory {seed}",
        "summary": f"governed memory summary {seed}",
        "content": f"strict governed memory content with durable recall token {seed}",
        "trace_id": f"trace-governance-{seed}",
        "tags": ["memory-governance", seed],
        "confidence_score": 0.82,
        "verification_status": "verified",
    }
    data.update(overrides)
    return EnhancedMemoryRecord(**data)


def _promote_local(governance: MemoryGovernance, memory: EnhancedMemoryRecord, seed: str) -> None:
    governance.submit_quarantined_memory(
        memory,
        source_instance_id=governance.instance_id,
        contamination_chain=_chain(seed),
        operator="ci",
    )
    governance.promote_memory(memory.memory_id, target_trust_level=MemoryTrustLevel.VERIFIED, reviewer_id="ci-reviewer")


def test_memory_governance_direct_package_import_revoke_and_contamination_are_queryable() -> None:
    seed = unique_suffix()
    sender = MemoryGovernance(instance_id=f"sender-{seed}", package_secret=f"secret-{seed}")
    receiver = MemoryGovernance(instance_id=f"receiver-{seed}", package_secret=f"secret-{seed}")
    sender_memory = _memory(seed)

    _promote_local(sender, sender_memory, seed)
    package = sender.export_package(
        [sender_memory.memory_id],
        target_instance_id=receiver.instance_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert package.encrypted_payload
    assert package.source_instance_id == sender.instance_id
    assert package.target_instance_id == receiver.instance_id
    assert package.binding_hash

    grant = receiver.authorize_package_import(
        package_id=package.package_id,
        source_instance_id=sender.instance_id,
        target_instance_id=receiver.instance_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        authorized_by="ci-authorizer",
    )
    imported = receiver.import_package(
        package,
        import_id=grant.import_id,
        contamination_chain=_chain(seed),
        operator="ci-importer",
    )
    assert imported.imported_memory_ids == [sender_memory.memory_id]
    assert len(imported.gate_decisions) == 1
    assert imported.gate_decisions[0].outcome == "accepted"
    assert len(imported.gate_decisions[0].gate_results) == 9
    assert imported.gate_decisions[0].failed_gate_ids == []
    quarantined = receiver.list_quarantine()
    assert len(quarantined) == 1
    assert quarantined[0].memory.memory_id == sender_memory.memory_id
    assert quarantined[0].trust_level == MemoryTrustLevel.UNTRUSTED
    assert receiver.recall_memories(seed) == []

    promoted = receiver.promote_memory(
        sender_memory.memory_id,
        target_trust_level=MemoryTrustLevel.VERIFIED,
        reviewer_id="ci-reviewer",
    )
    assert promoted.can_recall is True
    recall_hits = receiver.recall_memories(seed)
    assert [row.memory.memory_id for row in recall_hits] == [sender_memory.memory_id]

    revoked_grant = receiver.revoke_package_import(package.package_id, reason="source package revoked", operator="ci")
    assert revoked_grant.status.value == "revoked"
    assert receiver.recall_memories(seed) == []
    assert receiver.list_quarantine()[0].trust_level.value == "revoked"

    local_memory = _memory(f"{seed}-local")
    _promote_local(receiver, local_memory, f"{seed}-local")
    assert receiver.recall_memories(f"{seed}-local")[0].memory.memory_id == local_memory.memory_id
    contamination = receiver.mark_contamination(
        source_memory_id=local_memory.memory_id,
        impact_graph={
            "runtime_memory": [local_memory.memory_id],
            "goal": [f"goal-{seed}"],
            "action": [f"action-{seed}"],
            "execution": [f"execution-{seed}"],
            "reflection": [f"reflection-{seed}"],
        },
        operator="ci-contamination",
    )
    assert local_memory.memory_id in contamination.affected_memory_ids
    assert receiver.recall_memories(f"{seed}-local") == []
    rollback = receiver.rollback_contamination(contamination.contamination_id, operator="ci-rollback")
    assert rollback.revoked_memory_ids == contamination.affected_memory_ids
    assert [item.split(":", 1)[0] for item in rollback.rollback_trace] == [
        "runtime_memory",
        "goal",
        "action",
        "execution",
        "reflection",
    ]
    assert receiver.list_contamination()[0].status == "rolled_back"
    assert receiver.list_rollbacks()[0].rollback_id == rollback.rollback_id
    assert {"package_imported", "import_revoked", "contamination_rollback"} <= {
        event.action for event in receiver.list_memory_governance_audit_events()
    }


def test_memory_governance_rejects_any_gate_failure_and_preserves_forensic_state() -> None:
    seed = unique_suffix()
    governance = MemoryGovernance(instance_id=f"receiver-{seed}", package_secret=f"secret-{seed}")
    tampered = _memory(seed).model_copy(update={"content_hash": "0" * 64})

    with pytest.raises(MemoryRejectedError) as exc_info:
        governance.submit_quarantined_memory(
            tampered,
            source_instance_id=governance.instance_id,
            contamination_chain=_chain(seed),
            operator="ci-reject",
        )

    decision = exc_info.value.decision
    assert decision.outcome == "rejected"
    assert decision.failed_gate_ids == ["G1_content_integrity"]
    assert len(decision.gate_results) == 9
    assert governance.list_quarantine()[0].status.value == "rejected"
    assert governance.list_quarantine()[0].gate_decision.failed_gate_ids == ["G1_content_integrity"]
    assert governance.recall_memories(seed) == []
    assert governance.list_memory_governance_audit_events()[0].action == "quarantine_rejected"

    missing_chain_memory = _memory(f"{seed}-chain")
    with pytest.raises(MemoryRejectedError) as chain_exc:
        governance.submit_quarantined_memory(
            missing_chain_memory,
            source_instance_id=governance.instance_id,
            contamination_chain={"runtime_memory": [missing_chain_memory.memory_id]},
            operator="ci-reject",
        )
    assert chain_exc.value.decision.failed_gate_ids == ["G9_contamination_chain"]
    assert governance.recall_memories(f"{seed}-chain") == []


def test_memory_service_g38_methods_are_thin_real_delegates(tmp_path) -> None:
    seed = unique_suffix()
    service = MemoryService(storage_root=tmp_path / "receiver")
    sender_service = MemoryService(storage_root=tmp_path / "sender")
    receiver_governance = service.get_memory_governance()
    sender_governance = sender_service.get_memory_governance()
    memory = _memory(seed)

    sender_service.submit_quarantined_memory(
        memory,
        source_instance_id=sender_governance.instance_id,
        contamination_chain=_chain(seed),
        operator="ci-service",
    )
    sender_service.promote_memory(
        memory.memory_id,
        target_trust_level=MemoryTrustLevel.VERIFIED,
        reviewer_id="ci-service-reviewer",
    )
    assert sender_service.recall_memories(seed)[0].memory.memory_id == memory.memory_id
    package = sender_service.export_package(
        [memory.memory_id],
        target_instance_id=receiver_governance.instance_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    grant = service.authorize_package_import(
        package_id=package.package_id,
        source_instance_id=sender_governance.instance_id,
        target_instance_id=receiver_governance.instance_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        authorized_by="ci-service-authorizer",
    )
    imported = service.import_package(
        package,
        import_id=grant.import_id,
        contamination_chain=_chain(seed),
        operator="ci-service-importer",
    )
    assert imported.imported_memory_ids == [memory.memory_id]
    service.promote_memory(memory.memory_id, target_trust_level=MemoryTrustLevel.VERIFIED, reviewer_id="ci-service")
    assert service.recall_memories(seed)[0].memory.memory_id == memory.memory_id
    assert service.list_quarantine()[0].memory.memory_id == memory.memory_id
    assert service.list_main_memory()[0].memory.memory_id == memory.memory_id
    assert service.list_imports()[0].import_id == grant.import_id

    extra_memory = _memory(f"{seed}-extra")
    service.submit_quarantined_memory(
        extra_memory,
        source_instance_id=receiver_governance.instance_id,
        contamination_chain=_chain(f"{seed}-extra"),
        operator="ci-service",
    )
    service.promote_memory(extra_memory.memory_id, target_trust_level=MemoryTrustLevel.TENTATIVE, reviewer_id="ci")
    revoked = service.revoke_memory(extra_memory.memory_id, reason="direct revoke check", operator="ci")
    assert revoked.can_recall is False
    assert service.recall_memories(f"{seed}-extra") == []

    contamination = service.mark_contamination(
        source_memory_id=memory.memory_id,
        impact_graph={
            "runtime_memory": [memory.memory_id],
            "goal": [f"goal-{seed}"],
            "action": [f"action-{seed}"],
            "execution": [f"execution-{seed}"],
            "reflection": [f"reflection-{seed}"],
        },
        operator="ci",
    )
    rollback = service.rollback_contamination(contamination.contamination_id, operator="ci")
    assert rollback.contamination_id == contamination.contamination_id
    assert service.list_contamination()[0].contamination_id == contamination.contamination_id
    assert service.list_rollbacks()[0].rollback_id == rollback.rollback_id
    assert service.revoke_package_import(package.package_id, reason="package revoke check", operator="ci").status.value == "revoked"
    assert service.list_memory_governance_audit_events()


def test_memory_governance_api_uses_requests_and_verifies_read_after_write(acceptance_app: FastAPI, tmp_path) -> None:
    seed = unique_suffix()
    service = MemoryService(storage_root=tmp_path / "api-receiver")
    sender = MemoryGovernance(instance_id=f"api-sender-{seed}")
    acceptance_app.state.memory_service = service
    local_memory = _memory(seed)

    with live_http_server(acceptance_app) as base_url:
        quarantine_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/quarantine",
            json={
                "memory": local_memory.model_dump(mode="json"),
                "source_instance_id": service.get_memory_governance().instance_id,
                "contamination_chain": _chain(seed),
                "operator": "api-ci",
            },
            timeout=10,
        )
        assert quarantine_response.status_code == 200, quarantine_response.text
        assert quarantine_response.json()["gate_decision"]["failed_gate_ids"] == []

        promote_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/memories/{local_memory.memory_id}/promote",
            json={"target_trust_level": "verified", "reviewer_id": "api-reviewer"},
            timeout=10,
        )
        assert promote_response.status_code == 200, promote_response.text
        assert promote_response.json()["can_recall"] is True

        recall_response = requests.get(
            f"{base_url}/api/web/memory-governance/g38/recall",
            params={"query": seed},
            timeout=10,
        )
        assert recall_response.status_code == 200, recall_response.text
        assert [row["memory"]["memory_id"] for row in recall_response.json()] == [local_memory.memory_id]

        export_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/packages/export",
            json={
                "memory_ids": [local_memory.memory_id],
                "target_instance_id": service.get_memory_governance().instance_id,
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
            timeout=10,
        )
        assert export_response.status_code == 200, export_response.text
        assert export_response.json()["encrypted_payload"]

        sender_memory = _memory(f"{seed}-import")
        _promote_local(sender, sender_memory, f"{seed}-import")
        package = sender.export_package(
            [sender_memory.memory_id],
            target_instance_id=service.get_memory_governance().instance_id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        authorize_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/imports/authorize",
            json={
                "package_id": package.package_id,
                "source_instance_id": sender.instance_id,
                "target_instance_id": service.get_memory_governance().instance_id,
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "authorized_by": "api-authorizer",
            },
            timeout=10,
        )
        assert authorize_response.status_code == 200, authorize_response.text
        import_id = authorize_response.json()["import_id"]

        import_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/packages/import",
            json={
                "package": package.model_dump(mode="json"),
                "import_id": import_id,
                "contamination_chain": _chain(f"{seed}-import"),
                "operator": "api-importer",
            },
            timeout=10,
        )
        assert import_response.status_code == 200, import_response.text
        assert import_response.json()["imported_memory_ids"] == [sender_memory.memory_id]

        promote_import_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/memories/{sender_memory.memory_id}/promote",
            json={"target_trust_level": "verified", "reviewer_id": "api-reviewer"},
            timeout=10,
        )
        assert promote_import_response.status_code == 200, promote_import_response.text
        imported_recall = requests.get(
            f"{base_url}/api/web/memory-governance/g38/recall",
            params={"query": f"{seed}-import"},
            timeout=10,
        )
        assert [row["memory"]["memory_id"] for row in imported_recall.json()] == [sender_memory.memory_id]

        contamination_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/contamination",
            json={
                "source_memory_id": sender_memory.memory_id,
                "impact_graph": {
                    "runtime_memory": [sender_memory.memory_id],
                    "goal": [f"goal-{seed}"],
                    "action": [f"action-{seed}"],
                    "execution": [f"execution-{seed}"],
                    "reflection": [f"reflection-{seed}"],
                },
                "operator": "api-contamination",
            },
            timeout=10,
        )
        assert contamination_response.status_code == 200, contamination_response.text
        contamination_id = contamination_response.json()["contamination_id"]
        assert requests.get(
            f"{base_url}/api/web/memory-governance/g38/recall",
            params={"query": f"{seed}-import"},
            timeout=10,
        ).json() == []

        rollback_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/contamination/{contamination_id}/rollback",
            timeout=10,
        )
        assert rollback_response.status_code == 200, rollback_response.text
        assert rollback_response.json()["contamination_id"] == contamination_id

        revoke_memory_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/memories/{local_memory.memory_id}/revoke",
            json={"reason": "api revoke local", "operator": "api"},
            timeout=10,
        )
        assert revoke_memory_response.status_code == 200, revoke_memory_response.text
        assert requests.get(
            f"{base_url}/api/web/memory-governance/g38/recall",
            params={"query": seed},
            timeout=10,
        ).json() == []

        revoke_package_response = requests.post(
            f"{base_url}/api/web/memory-governance/g38/packages/{package.package_id}/revoke",
            json={"reason": "api package revoked", "operator": "api"},
            timeout=10,
        )
        assert revoke_package_response.status_code == 200, revoke_package_response.text
        assert revoke_package_response.json()["status"] == "revoked"

        assert requests.get(f"{base_url}/api/web/memory-governance/g38/quarantine", timeout=10).status_code == 200
        assert requests.get(f"{base_url}/api/web/memory-governance/g38/main-memory", timeout=10).json() == []
        assert requests.get(f"{base_url}/api/web/memory-governance/g38/imports", timeout=10).json()[0]["status"] == "revoked"
        assert requests.get(f"{base_url}/api/web/memory-governance/g38/contamination", timeout=10).json()[0]["status"] == "rolled_back"
        assert requests.get(f"{base_url}/api/web/memory-governance/g38/rollbacks", timeout=10).json()[0]["contamination_id"] == contamination_id
        audit_actions = {
            row["action"]
            for row in requests.get(f"{base_url}/api/web/memory-governance/g38/audit", timeout=10).json()
        }
        assert {"quarantine_accepted", "package_imported", "memory_revoked"} <= audit_actions
