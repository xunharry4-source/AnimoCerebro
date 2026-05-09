from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.collaboration.secure_communication import SecureCollaborationRuntime


def test_secure_collaboration_api_signs_verifies_encrypts_rejects_replay_and_revokes_real_requests(
    acceptance_app: FastAPI,
    tmp_path: Path,
) -> None:
    keystore_path = tmp_path / "identity_keystore"
    keystore_secret = f"keystore-secret-{uuid4().hex}"
    acceptance_app.state.secure_collaboration_runtime = SecureCollaborationRuntime(
        keystore_path=keystore_path,
        keystore_secret=keystore_secret,
    )
    suffix = uuid4().hex
    alice = f"secure-alice-{suffix}"
    bob = f"secure-bob-{suffix}"
    before_audit_count = len(acceptance_app.state.transcript_store.entries)

    with live_http_server(acceptance_app) as base_url:
        alice_identity = requests.post(
            f"{base_url}/api/web/collaboration/security/identities",
            json={"brain_id": alice, "tofu_confirmed_by": "operator-a"},
            timeout=10,
        )
        assert alice_identity.status_code == 200, alice_identity.text
        alice_payload = alice_identity.json()
        assert alice_payload["brain_id"] == alice
        assert alice_payload["key_id"].startswith("brain-key:")
        assert alice_payload["private_key_exported"] is False
        assert "private" not in alice_payload["signing_public_key_b64"].lower()
        stored_identity_files = list(keystore_path.glob("*.identity.json"))
        assert len(stored_identity_files) == 1
        stored_identity_text = stored_identity_files[0].read_text(encoding="utf-8")
        assert alice_payload["signing_public_key_b64"] not in stored_identity_text
        assert alice not in stored_identity_files[0].name
        assert "signing_private_key_b64" not in stored_identity_text
        assert "ecdh_private_key_b64" not in stored_identity_text

        duplicate_identity = requests.post(
            f"{base_url}/api/web/collaboration/security/identities",
            json={"brain_id": alice, "tofu_confirmed_by": "operator-a"},
            timeout=10,
        )
        assert duplicate_identity.status_code == 409
        assert "active identity already exists" in duplicate_identity.json()["detail"]

        bob_identity = requests.post(
            f"{base_url}/api/web/collaboration/security/identities",
            json={"brain_id": bob, "tofu_confirmed_by": "operator-b"},
            timeout=10,
        )
        assert bob_identity.status_code == 200, bob_identity.text
        bob_payload = bob_identity.json()

        public_keys = requests.get(f"{base_url}/api/web/collaboration/security/public-keys", timeout=10)
        assert public_keys.status_code == 200
        public_key_rows = {item["brain_id"]: item for item in public_keys.json()}
        assert public_key_rows[alice]["status"] == "active"
        assert public_key_rows[bob]["status"] == "active"
        assert public_key_rows[alice]["tofu_confirmed_by"] == "operator-a"
        assert all("private" not in key for row in public_key_rows.values() for key in row)

        blank_tofu = deepcopy(public_key_rows[alice])
        blank_tofu["brain_id"] = f"untrusted-{suffix}"
        blank_tofu["key_id"] = f"brain-key:untrusted{suffix[:16]}"
        blank_tofu["tofu_confirmed_by"] = " "
        tofu_rejected = requests.post(
            f"{base_url}/api/web/collaboration/security/public-keys",
            json=blank_tofu,
            timeout=10,
        )
        assert tofu_rejected.status_code == 409
        assert "TOFU confirmation is required" in tofu_rejected.json()["detail"]

        forged_key_id = deepcopy(public_key_rows[alice])
        forged_key_id["brain_id"] = f"forged-key-id-{suffix}"
        forged_key_id["key_id"] = f"brain-key:forged{suffix[:16]}"
        forged_key_id["tofu_confirmed_by"] = "operator-c"
        forged_key_rejected = requests.post(
            f"{base_url}/api/web/collaboration/security/public-keys",
            json=forged_key_id,
            timeout=10,
        )
        assert forged_key_rejected.status_code == 409
        assert "key_id does not match signing public key" in forged_key_rejected.json()["detail"]

        acceptance_app.state.secure_collaboration_runtime = SecureCollaborationRuntime(
            keystore_path=keystore_path,
            keystore_secret=f"wrong-secret-{suffix}",
        )
        wrong_secret_load = requests.post(
            f"{base_url}/api/web/collaboration/security/identities/load",
            json={"brain_id": alice},
            timeout=10,
        )
        assert wrong_secret_load.status_code == 409
        assert wrong_secret_load.json()["detail"]

        acceptance_app.state.secure_collaboration_runtime = SecureCollaborationRuntime(
            keystore_path=keystore_path,
            keystore_secret=keystore_secret,
        )
        loaded_alice = requests.post(
            f"{base_url}/api/web/collaboration/security/identities/load",
            json={"brain_id": alice},
            timeout=10,
        )
        assert loaded_alice.status_code == 200, loaded_alice.text
        assert loaded_alice.json()["key_id"] == alice_payload["key_id"]
        loaded_bob = requests.post(
            f"{base_url}/api/web/collaboration/security/identities/load",
            json={"brain_id": bob},
            timeout=10,
        )
        assert loaded_bob.status_code == 200
        assert loaded_bob.json()["key_id"] == bob_payload["key_id"]

        signed = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/sign",
            json={
                "sender_brain_id": alice,
                "receiver_brain_id": "broadcast",
                "message_type": "TaskAnnouncement",
                "payload": {"task_id": f"task-{suffix}", "domain": "risk", "priority": "high"},
            },
            timeout=10,
        )
        assert signed.status_code == 200, signed.text
        signed_message = signed.json()
        assert signed_message["header"]["sender_key_id"] == alice_payload["key_id"]
        assert signed_message["header"]["signature"]
        assert signed_message["header"]["encrypted"] is False
        assert signed_message["payload"]["task_id"] == f"task-{suffix}"
        assert signed_message["encrypted_payload"] is None

        verified = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/verify",
            json=signed_message,
            timeout=10,
        )
        assert verified.status_code == 200, verified.text
        verified_payload = verified.json()
        assert verified_payload["accepted"] is True
        assert verified_payload["sender_brain_id"] == alice
        assert verified_payload["sender_key_id"] == alice_payload["key_id"]
        assert verified_payload["message_type"] == "TaskAnnouncement"
        assert verified_payload["decrypted_payload"] == signed_message["payload"]

        replay = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/verify",
            json=signed_message,
            timeout=10,
        )
        assert replay.status_code == 409
        assert "replay nonce" in replay.json()["detail"]

        tamper_source = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/sign",
            json={
                "sender_brain_id": alice,
                "receiver_brain_id": "broadcast",
                "message_type": "ConsensusVote",
                "payload": {"proposal_id": f"proposal-{suffix}", "decision": "approve"},
            },
            timeout=10,
        )
        assert tamper_source.status_code == 200
        tampered_message = tamper_source.json()
        tampered_message["payload"]["decision"] = "poisoned"
        tampered = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/verify",
            json=tampered_message,
            timeout=10,
        )
        assert tampered.status_code == 409
        assert "payload hash mismatch" in tampered.json()["detail"]

        nonsensitive_encryption = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/sign",
            json={
                "sender_brain_id": alice,
                "receiver_brain_id": bob,
                "message_type": "TaskAnnouncement",
                "payload": {"task_id": f"plain-{suffix}"},
                "encrypt_for_receiver": True,
            },
            timeout=10,
        )
        assert nonsensitive_encryption.status_code == 409
        assert "high-sensitivity" in nonsensitive_encryption.json()["detail"]

        broadcast_encryption = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/sign",
            json={
                "sender_brain_id": alice,
                "receiver_brain_id": "broadcast",
                "message_type": "ExperienceExchangePacket",
                "payload": {"secret": f"broadcast-secret-{suffix}"},
                "encrypt_for_receiver": True,
            },
            timeout=10,
        )
        assert broadcast_encryption.status_code == 409
        assert "broadcast messages cannot" in broadcast_encryption.json()["detail"]

        secret_payload = {
            "experience_id": f"exp-{suffix}",
            "secret_patch": f"do-not-leak-{suffix}",
            "risk_level": "high",
        }
        encrypted = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/sign",
            json={
                "sender_brain_id": alice,
                "receiver_brain_id": bob,
                "message_type": "ExperienceExchangePacket",
                "payload": secret_payload,
                "encrypt_for_receiver": True,
            },
            timeout=10,
        )
        assert encrypted.status_code == 200, encrypted.text
        encrypted_message = encrypted.json()
        assert encrypted_message["header"]["encrypted"] is True
        assert encrypted_message["payload"] is None
        assert encrypted_message["encrypted_payload"]["ciphertext_b64"]
        assert secret_payload["secret_patch"] not in encrypted_message["encrypted_payload"]["ciphertext_b64"]

        decrypted = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/verify",
            json=encrypted_message,
            timeout=10,
        )
        assert decrypted.status_code == 200, decrypted.text
        assert decrypted.json()["decrypted_payload"] == secret_payload

        revocation_notice = requests.post(
            f"{base_url}/api/web/collaboration/security/revocations/sign",
            json={
                "revoker_brain_id": alice,
                "target_brain_id": bob,
                "target_key_id": bob_payload["key_id"],
                "reason": "compromised test key",
            },
            timeout=10,
        )
        assert revocation_notice.status_code == 200, revocation_notice.text
        notice_payload = revocation_notice.json()
        forged_notice = deepcopy(notice_payload)
        forged_notice["reason"] = "forged revocation reason"
        rejected_notice = requests.post(
            f"{base_url}/api/web/collaboration/security/revocations/apply",
            json=forged_notice,
            timeout=10,
        )
        assert rejected_notice.status_code == 409
        assert "InvalidSignature" in rejected_notice.json()["detail"]

        applied_revocation = requests.post(
            f"{base_url}/api/web/collaboration/security/revocations/apply",
            json=notice_payload,
            timeout=10,
        )
        assert applied_revocation.status_code == 200, applied_revocation.text
        assert applied_revocation.json()["brain_id"] == bob
        assert applied_revocation.json()["key_id"] == bob_payload["key_id"]
        assert applied_revocation.json()["status"] == "revoked"

        bob_key_after_revoke = requests.get(
            f"{base_url}/api/web/collaboration/security/public-keys/{bob}",
            timeout=10,
        )
        assert bob_key_after_revoke.status_code == 200
        assert bob_key_after_revoke.json()["status"] == "revoked"

        revoked_sender_message = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/sign",
            json={
                "sender_brain_id": bob,
                "receiver_brain_id": "broadcast",
                "message_type": "TaskAnnouncement",
                "payload": {"task_id": f"revoked-{suffix}"},
            },
            timeout=10,
        )
        assert revoked_sender_message.status_code == 200
        revoked_sender_verify = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/verify",
            json=revoked_sender_message.json(),
            timeout=10,
        )
        assert revoked_sender_verify.status_code == 409
        assert "sender key is revoked" in revoked_sender_verify.json()["detail"]

        rotation = requests.post(
            f"{base_url}/api/web/collaboration/security/identities/rotate",
            json={"brain_id": alice, "reason": "scheduled rotation", "tofu_confirmed_by": "operator-a"},
            timeout=10,
        )
        assert rotation.status_code == 200, rotation.text
        rotation_payload = rotation.json()
        assert rotation_payload["old_key_id"] == alice_payload["key_id"]
        assert rotation_payload["new_key_id"] != alice_payload["key_id"]
        assert rotation_payload["old_key_status"] == "revoked"
        assert rotation_payload["new_key_status"] == "active"

        rotated_public = requests.get(f"{base_url}/api/web/collaboration/security/public-keys/{alice}", timeout=10)
        assert rotated_public.status_code == 200
        assert rotated_public.json()["key_id"] == rotation_payload["new_key_id"]
        assert rotated_public.json()["status"] == "active"

        old_key_message_rejected = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/verify",
            json=signed_message,
            timeout=10,
        )
        assert old_key_message_rejected.status_code == 409
        assert "sender_key_id does not match registry" in old_key_message_rejected.json()["detail"]

        rotated_message = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/sign",
            json={
                "sender_brain_id": alice,
                "receiver_brain_id": "broadcast",
                "message_type": "TaskAnnouncement",
                "payload": {"task_id": f"rotated-{suffix}"},
            },
            timeout=10,
        )
        assert rotated_message.status_code == 200
        assert rotated_message.json()["header"]["sender_key_id"] == rotation_payload["new_key_id"]
        rotated_verify = requests.post(
            f"{base_url}/api/web/collaboration/security/messages/verify",
            json=rotated_message.json(),
            timeout=10,
        )
        assert rotated_verify.status_code == 200, rotated_verify.text
        assert rotated_verify.json()["accepted"] is True

        incidents = requests.get(f"{base_url}/api/web/collaboration/security/incidents", timeout=10)
        assert incidents.status_code == 200
        incident_rows = incidents.json()
        incident_reasons = [item["reason"] for item in incident_rows]
        assert len(incident_rows) >= 5
        assert any("replay nonce" in reason for reason in incident_reasons)
        assert any("payload hash mismatch" in reason for reason in incident_reasons)
        assert any("InvalidSignature" in reason for reason in incident_reasons)
        assert any("sender key is revoked" in reason for reason in incident_reasons)
        assert any("sender_key_id does not match registry" in reason for reason in incident_reasons)
        assert all(item["action_taken"] in {"reject_without_processing_payload", "reject_revocation_notice"} for item in incident_rows)
        assert incident_rows[0]["previous_event_hash"] == ""
        assert incident_rows[0]["event_hash"]
        for previous, current in zip(incident_rows, incident_rows[1:]):
            assert current["previous_event_hash"] == previous["event_hash"]

    new_audits = acceptance_app.state.transcript_store.entries[before_audit_count:]
    audit_payloads = [item["payload"] for item in new_audits]
    assert sum(1 for item in audit_payloads if item["event_type"] == "brain_identity_created") == 2
    assert sum(1 for item in audit_payloads if item["event_type"] == "brain_identity_loaded") == 2
    assert any(item["event_type"] == "brain_identity_rotated" and item["new_key_id"] == rotation_payload["new_key_id"] for item in audit_payloads)
    assert any(item["event_type"] == "brain_message_verified" and item["message_type"] == "TaskAnnouncement" for item in audit_payloads)
    assert any(item["event_type"] == "brain_message_verified" and item["message_type"] == "ExperienceExchangePacket" for item in audit_payloads)
    assert any(item["event_type"] == "brain_key_revoked" and item["target_brain_id"] == bob for item in audit_payloads)
