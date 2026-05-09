from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import socket
import threading
import time

import pytest
import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.collaboration.experience_exchange import (
    ApplicableExperienceScope,
    ExperienceAdoptionReview,
    ExperienceExchange,
    ExperienceExchangeConfig,
    ExperienceType,
    ExperienceReviewConclusion,
)
from zentex.collaboration.service import CollaborationService


@contextmanager
def _live_http_server(app: FastAPI) -> Iterator[str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(app, host=host, port=port, log_level="critical", lifespan="off", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and thread.is_alive() and time.time() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        raise RuntimeError("uvicorn live request server failed to start")
    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _sender_receiver(suffix: str) -> tuple[ExperienceExchange, ExperienceExchange]:
    sender_id = f"g37-sender-{suffix}"
    receiver_id = f"g37-receiver-{suffix}"
    sender_secret = f"sender-secret-{suffix}"
    receiver_secret = f"receiver-secret-{suffix}"
    sender = ExperienceExchange(
        ExperienceExchangeConfig(
            brain_id=sender_id,
            signing_key=sender_secret,
            local_domains=["python"],
            local_roles=["developer"],
            local_risk_levels=["low", "medium", "high"],
            local_env_types=["ci"],
        )
    )
    receiver = ExperienceExchange(
        ExperienceExchangeConfig(
            brain_id=receiver_id,
            signing_key=receiver_secret,
            verification_keys={sender_id: sender_secret},
            local_domains=["python"],
            local_roles=["developer"],
            local_risk_levels=["low", "medium", "high"],
            local_env_types=["ci"],
            trust_threshold=0.4,
        )
    )
    return sender, receiver


def test_g37_packet_quarantine_review_promotion_contamination_and_rollback_are_queryable() -> None:
    suffix = unique_suffix()
    sender, receiver = _sender_receiver(suffix)
    packet = sender.create_packet(
        experience_type=ExperienceType.STRATEGY_PATCH_SUGGESTION,
        payload={"lesson": "retry parser backoff after schema mismatch", "patch_hint": f"g37-{suffix}"},
        applicable_scope=ApplicableExperienceScope(
            applicable_domains=["python"],
            applicable_roles=["developer"],
            applicable_risk_levels=["medium"],
            applicable_env_types=["ci"],
        ),
        trust_score=0.82,
        risk_level="high",
    )
    assert packet.signature.startswith("hmac-sha256=")

    review = receiver.receive_packet(packet)
    assert review.conclusion == ExperienceReviewConclusion.PENDING
    assert review.adoption_conditions["status"] == "quarantine"
    quarantine = receiver.list_quarantine()
    assert len(quarantine) == 1
    assert quarantine[0].packet.experience_id == packet.experience_id
    assert quarantine[0].trust_level.value == "untrusted"
    assert quarantine[0].can_drive_decisions is False

    payload = receiver.use_quarantined_experience(packet.experience_id, for_prompting_only=True)
    assert payload["patch_hint"] == f"g37-{suffix}"
    assert receiver.list_quarantine()[0].usage_count == 1
    with pytest.raises(ValueError, match="cannot drive decisions"):
        receiver.use_quarantined_experience(packet.experience_id, for_prompting_only=False)
    with pytest.raises(ValueError, match="explicit human/cloud audit review"):
        receiver.promote(packet.experience_id, reviewer_id="reviewer-before-approval")

    approved = receiver.submit_review(
        ExperienceAdoptionReview(
            experience_id=packet.experience_id,
            conclusion=ExperienceReviewConclusion.APPROVED,
            reviewer_id="human-reviewer",
            adoption_conditions={"allowed_promotion": "tentative_then_verified"},
        )
    )
    assert approved.reviewer_id == "human-reviewer"
    tentative = receiver.promote(packet.experience_id, reviewer_id="human-reviewer")
    assert tentative.trust_level.value == "tentative"
    assert tentative.can_drive_decisions is False
    verified = receiver.promote(packet.experience_id, reviewer_id="human-reviewer")
    assert verified.trust_level.value == "verified"
    assert verified.can_drive_decisions is True
    assert receiver.list_adopted()[0].packet.experience_id == packet.experience_id
    assert receiver.list_quarantine() == []

    influence = receiver.record_decision_influence(
        experience_id=packet.experience_id,
        affected_brain_id=receiver.config.brain_id,
        decision_id=f"decision-{suffix}",
        patch_id=f"patch-{suffix}",
    )
    assert influence["affected_decisions"] == [f"decision-{suffix}"]
    contamination = receiver.mark_contamination(experience_id=packet.experience_id)
    assert contamination.source_experience_id == packet.experience_id
    assert contamination.affected_decisions == [f"decision-{suffix}"]
    assert contamination.affected_patches == [f"patch-{suffix}"]
    assert receiver.list_adopted() == []
    contaminated_entry = receiver.list_quarantine()[0]
    assert contaminated_entry.trust_level.value == "revoked"
    assert contaminated_entry.packet.contamination_trace_id == contamination.contamination_id

    rollback = receiver.execute_rollback(contamination.contamination_id, rollback_scope="full")
    assert rollback.success_count == 1
    assert f"decision-{suffix}" in ",".join(rollback.revoked_experiences)
    assert f"patch-{suffix}" in ",".join(rollback.revoked_experiences)
    assert receiver.list_contamination()[0].resolved_at is not None
    assert receiver.list_rollbacks()[0].rollback_id == rollback.rollback_id
    assert "contamination_rollback_executed" in {event.action for event in receiver.list_audit_events()}


def test_g37_rejects_tampered_forbidden_low_trust_and_scope_mismatch_packets() -> None:
    suffix = unique_suffix()
    sender, receiver = _sender_receiver(suffix)

    clean = sender.create_packet(
        experience_type=ExperienceType.EXPERIENCE,
        payload={"lesson": "valid payload before tamper", "suffix": suffix},
        applicable_scope=ApplicableExperienceScope(applicable_domains=["python"]),
        trust_score=0.9,
        risk_level="low",
    )
    tampered = clean.model_copy(update={"payload": {"lesson": "tampered after signature", "suffix": suffix}})
    tampered_review = receiver.receive_packet(tampered)
    assert tampered_review.conclusion == ExperienceReviewConclusion.REJECTED
    assert tampered_review.block_reason == "signature verification failed"

    with pytest.raises(ValueError, match="forbidden"):
        sender.create_packet(
            experience_type=ExperienceType.EXPERIENCE,
            payload={"_type": "identity_kernel", "secret_token": "must-not-share"},
            applicable_scope=ApplicableExperienceScope(applicable_domains=["python"]),
            trust_score=0.9,
        )

    low_trust = sender.create_packet(
        experience_type=ExperienceType.FAILURE_CASE,
        payload={"failure": "low trust sample"},
        applicable_scope=ApplicableExperienceScope(applicable_domains=["python"]),
        trust_score=0.1,
    )
    low_review = receiver.receive_packet(low_trust)
    assert low_review.conclusion == ExperienceReviewConclusion.REJECTED
    assert "below threshold" in str(low_review.block_reason)

    wrong_scope = sender.create_packet(
        experience_type=ExperienceType.ENVIRONMENT_OBSERVATION,
        payload={"observation": "frontend only"},
        applicable_scope=ApplicableExperienceScope(applicable_domains=["frontend"], applicable_env_types=["browser"]),
        trust_score=0.9,
    )
    scope_review = receiver.receive_packet(wrong_scope)
    assert scope_review.conclusion == ExperienceReviewConclusion.REJECTED
    assert scope_review.block_reason == "not applicable to receiver scope"
    rejections = receiver.list_rejections()
    assert [row.experience_id for row in rejections] == [
        tampered.experience_id,
        low_trust.experience_id,
        wrong_scope.experience_id,
    ]
    assert receiver.list_quarantine() == []
    assert receiver.list_adopted() == []


def test_g37_api_uses_real_requests_for_receive_review_promote_trace_rollback_and_revoke(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    sender, receiver = _sender_receiver(suffix)
    acceptance_app.state.collaboration_service = CollaborationService(experience_exchange=receiver)
    packet = sender.create_packet(
        experience_type=ExperienceType.RISK_SAMPLE,
        payload={"risk": "schema mismatch can trigger stale parser decisions", "suffix": suffix},
        applicable_scope=ApplicableExperienceScope(
            applicable_domains=["python"],
            applicable_roles=["developer"],
            applicable_risk_levels=["medium"],
            applicable_env_types=["ci"],
        ),
        trust_score=0.88,
        risk_level="high",
    )

    with _live_http_server(acceptance_app) as base_url:
        create_response = requests.post(
            f"{base_url}/api/web/collaboration/g37/packets",
            json={
                "experience_type": "experience",
                "payload": {"lesson": f"local packet creation is signed {suffix}"},
                "applicable_scope": {"applicable_domains": ["python"]},
                "trust_score": 0.7,
                "risk_level": "low",
            },
            timeout=10,
        )
        assert create_response.status_code == 200, create_response.text
        assert create_response.json()["signature"].startswith("hmac-sha256=")

        receive_response = requests.post(
            f"{base_url}/api/web/collaboration/g37/packets/receive",
            json=packet.model_dump(mode="json"),
            timeout=10,
        )
        assert receive_response.status_code == 200, receive_response.text
        assert receive_response.json()["conclusion"] == "pending"

        quarantine_response = requests.get(f"{base_url}/api/web/collaboration/g37/quarantine", timeout=10)
        assert quarantine_response.status_code == 200, quarantine_response.text
        assert quarantine_response.json()[0]["packet"]["experience_id"] == packet.experience_id
        assert quarantine_response.json()[0]["can_drive_decisions"] is False

        blocked_use = requests.post(
            f"{base_url}/api/web/collaboration/g37/quarantine/{packet.experience_id}/use",
            json={"for_prompting_only": False},
            timeout=10,
        )
        assert blocked_use.status_code == 409
        prompt_use = requests.post(
            f"{base_url}/api/web/collaboration/g37/quarantine/{packet.experience_id}/use",
            json={"for_prompting_only": True},
            timeout=10,
        )
        assert prompt_use.status_code == 200, prompt_use.text
        assert prompt_use.json()["suffix"] == suffix

        review_response = requests.post(
            f"{base_url}/api/web/collaboration/g37/reviews",
            json={
                "experience_id": packet.experience_id,
                "conclusion": "approved",
                "reviewer_id": "api-human-reviewer",
                "adoption_conditions": {"risk_sample_checked": True},
            },
            timeout=10,
        )
        assert review_response.status_code == 200, review_response.text
        assert review_response.json()["reviewer_id"] == "api-human-reviewer"

        first_promote = requests.post(
            f"{base_url}/api/web/collaboration/g37/quarantine/{packet.experience_id}/promote",
            json={"reviewer_id": "api-human-reviewer"},
            timeout=10,
        )
        assert first_promote.status_code == 200, first_promote.text
        assert first_promote.json()["trust_level"] == "tentative"
        second_promote = requests.post(
            f"{base_url}/api/web/collaboration/g37/quarantine/{packet.experience_id}/promote",
            json={"reviewer_id": "api-human-reviewer"},
            timeout=10,
        )
        assert second_promote.status_code == 200, second_promote.text
        assert second_promote.json()["trust_level"] == "verified"
        assert second_promote.json()["can_drive_decisions"] is True

        adopted_response = requests.get(f"{base_url}/api/web/collaboration/g37/adopted", timeout=10)
        assert adopted_response.status_code == 200, adopted_response.text
        assert adopted_response.json()[0]["packet"]["payload"]["suffix"] == suffix

        influence_response = requests.post(
            f"{base_url}/api/web/collaboration/g37/experiences/{packet.experience_id}/decision-influence",
            json={"affected_brain_id": receiver.config.brain_id, "decision_id": f"api-decision-{suffix}", "patch_id": f"api-patch-{suffix}"},
            timeout=10,
        )
        assert influence_response.status_code == 200, influence_response.text
        assert influence_response.json()["affected_patches"] == [f"api-patch-{suffix}"]

        contamination_response = requests.post(
            f"{base_url}/api/web/collaboration/g37/experiences/{packet.experience_id}/contamination",
            json={"affected_brain_ids": ["peer-a"], "affected_decisions": ["manual-extra-decision"], "affected_patches": []},
            timeout=10,
        )
        assert contamination_response.status_code == 200, contamination_response.text
        contamination_id = contamination_response.json()["contamination_id"]
        assert sorted(contamination_response.json()["affected_decisions"]) == [f"api-decision-{suffix}", "manual-extra-decision"]

        rollback_response = requests.post(
            f"{base_url}/api/web/collaboration/g37/contamination/{contamination_id}/rollback",
            json={"rollback_scope": "full"},
            timeout=10,
        )
        assert rollback_response.status_code == 200, rollback_response.text
        assert rollback_response.json()["failure_count"] == 0
        assert any(f"api-patch-{suffix}" in item for item in rollback_response.json()["revoked_experiences"])

        revoke_response = requests.post(
            f"{base_url}/api/web/collaboration/g37/experiences/{packet.experience_id}/revoke",
            json={"source_brain_id": packet.source_brain_id, "reason": "sender revoked after contamination"},
            timeout=10,
        )
        assert revoke_response.status_code == 200, revoke_response.text
        assert revoke_response.json()["reason"] == "sender revoked after contamination"

        final_quarantine = requests.get(f"{base_url}/api/web/collaboration/g37/quarantine", timeout=10)
        final_adopted = requests.get(f"{base_url}/api/web/collaboration/g37/adopted", timeout=10)
        revocations = requests.get(f"{base_url}/api/web/collaboration/g37/revocations", timeout=10)
        audit = requests.get(f"{base_url}/api/web/collaboration/g37/audit", timeout=10)

    assert final_quarantine.status_code == 200, final_quarantine.text
    quarantined = final_quarantine.json()
    assert quarantined[0]["packet"]["experience_id"] == packet.experience_id
    assert quarantined[0]["trust_level"] == "revoked"
    assert quarantined[0]["can_drive_decisions"] is False
    assert final_adopted.status_code == 200, final_adopted.text
    assert final_adopted.json() == []
    assert revocations.status_code == 200, revocations.text
    assert revocations.json()[0]["experience_id"] == packet.experience_id
    assert audit.status_code == 200, audit.text
    audit_actions = {row["action"] for row in audit.json()}
    assert {
        "packet_quarantined",
        "adoption_review_recorded",
        "experience_promoted",
        "decision_influence_recorded",
        "contamination_marked",
        "contamination_rollback_executed",
        "experience_revoked",
    }.issubset(audit_actions)
