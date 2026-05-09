from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import socket
import threading
import time

import pytest
import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.collaboration.organization_protocol import (
    OrganizationCompletionReview,
    OrganizationCompletionSubmission,
    OrganizationConversationTurn,
    OrganizationExceptionType,
    OrganizationGoalAnnouncement,
    OrganizationGoalClaim,
    OrganizationGoalDecline,
    OrganizationGoalProgress,
    OrganizationGroupExperiencePacket,
    OrganizationNodeHeartbeat,
    OrganizationProtocol,
    OrganizationSessionState,
    OrganizationSkillAnnouncement,
    OrganizationTaskItem,
)
from zentex.collaboration.service import CollaborationService


UTC = timezone.utc


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


def _service() -> CollaborationService:
    return CollaborationService(organization_protocol=OrganizationProtocol(heartbeat_ttl_seconds=300))


def test_g36_high_risk_claim_requires_confirmation_evidence_review_and_read_after_write() -> None:
    suffix = unique_suffix()
    service = _service()
    initiator = f"g36-initiator-{suffix}"
    worker = f"g36-worker-{suffix}"

    service.heartbeat(OrganizationNodeHeartbeat(brain_id=initiator, capabilities=["planning"], trust_score=0.95))
    service.heartbeat(OrganizationNodeHeartbeat(brain_id=worker, capabilities=["python", "evidence-review"], trust_score=0.9))
    skill = service.announce_skill(
        OrganizationSkillAnnouncement(
            brain_id=worker,
            skill_name="python",
            evidence_ref=f"capability-proof-{suffix}",
            source="real-ci",
            valid_until=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    queried_skills = service.query_capabilities("python")
    assert queried_skills[0].announcement_id == skill.announcement_id
    assert queried_skills[0].brain_id == worker

    task = OrganizationTaskItem(
        content="Implement a bounded parser handoff item",
        objective="return verified parser evidence",
        requirements=["python"],
        failure_strategy="retryable",
    )
    session = service.announce_goal(
        OrganizationGoalAnnouncement(
            initiator_brain_id=initiator,
            title=f"G36 high risk delegated parser task {suffix}",
            risk_level="high",
            acceptance_criteria=["parser output matches required schema"],
            required_evidence=["unit-test-log", "review-checklist"],
            task_breakdown=[task],
            idempotency_key=f"g36-session-{suffix}",
        )
    )
    queried_session = service.get_session(session.session_id)
    assert queried_session.security_review.accepted is True
    assert queried_session.task_breakdown[0].task_item_id == task.task_item_id
    assert queried_session.event_seq > 0

    claim = service.claim_goal(
        OrganizationGoalClaim(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            claimant_brain_id=worker,
            deliverables=["parser module", "unit-test-log", "review-checklist"],
            required_resources=["workspace"],
            eta_seconds=120,
            time_budget_seconds=600,
            token_budget=2000,
            retry_budget=2,
        )
    )
    assert claim.status.value == "waiting_confirmation"
    waiting_session = service.get_session(session.session_id)
    assert waiting_session.state == OrganizationSessionState.WAITING
    assert waiting_session.task_breakdown[0].owner_brain_id == worker

    confirmed = service.confirm_claim(claim.claim_id, confirmer_brain_id=initiator, accepted=True)
    assert confirmed.status.value == "accepted"
    active_session = service.get_session(session.session_id)
    assert active_session.state == OrganizationSessionState.ACTIVE
    assert active_session.task_breakdown[0].status.value == "claimed"

    progress = service.record_progress(
        OrganizationGoalProgress(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            reporter_brain_id=worker,
            percent_complete=60,
            status_note="parser implemented, evidence collection in progress",
            evidence_refs=["unit-test-log"],
        )
    )
    assert progress.overdue is False
    assert service.get_session(session.session_id).task_breakdown[0].status.value == "in_progress"

    with pytest.raises(ValueError, match="missing required evidence"):
        service.submit_completion(
            OrganizationCompletionSubmission(
                session_id=session.session_id,
                task_item_id=task.task_item_id,
                submitter_brain_id=worker,
                summary="parser completed but review checklist omitted",
                evidence_refs=["unit-test-log"],
            )
        )
    failures = service.list_failures(session.session_id)
    assert failures[-1].exception_type == OrganizationExceptionType.EVIDENCE_MISSING
    assert failures[-1].blocked_reason == "missing required evidence: review-checklist"
    assert service.get_session(session.session_id).state == OrganizationSessionState.BLOCKED

    submission = service.submit_completion(
        OrganizationCompletionSubmission(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            submitter_brain_id=worker,
            summary="parser completed with all evidence attached",
            evidence_refs=["unit-test-log", "review-checklist"],
            result_payload={"schema_valid": True, "suffix": suffix},
        )
    )
    review = service.review_completion(
        OrganizationCompletionReview(
            submission_id=submission.submission_id,
            reviewer_brain_id=initiator,
            accepted=True,
            checklist_results={"parser output matches required schema": True},
            reason="required evidence and schema checks match the announcement",
        )
    )
    assert review.accepted is True
    completed = service.get_session(session.session_id)
    assert completed.state == OrganizationSessionState.COMPLETED
    assert completed.final_ack is True
    assert completed.memory_write_gate is True
    assert completed.audit_closeout is True

    outcome = service.list_outcomes(session.session_id)[0]
    assert outcome.success is True
    assert "tail_cleanup" in outcome.next_actions

    packet = service.share_group_experience(
        OrganizationGroupExperiencePacket(
            source_session_id=session.session_id,
            source_brain_id=initiator,
            applicable_task_types=["delegated-parser"],
            lesson="high-risk G36 delegation must require confirmation and evidence review",
            evidence_refs=["unit-test-log", "review-checklist"],
        )
    )
    assert packet.status == "shared"
    audits = service.list_audit_events(session.session_id)
    assert [event.event_seq for event in audits] == sorted(event.event_seq for event in audits)
    assert {"goal_announcement", "goal_claim", "goal_completion_review", "group_experience_packet"}.issubset(
        {event.action for event in audits}
    )
    matrix = service.exception_matrix()
    assert matrix["heartbeat_lost"] == "reroute"
    assert matrix["evidence_missing"] == "revalidate"
    assert len(matrix) >= 21


def test_g36_cheating_reviews_accumulate_strikes_and_ban_future_claims() -> None:
    suffix = unique_suffix()
    service = _service()
    initiator = f"g36-ban-initiator-{suffix}"
    worker = f"g36-ban-worker-{suffix}"
    service.heartbeat(OrganizationNodeHeartbeat(brain_id=initiator, capabilities=["planning"], trust_score=0.95))
    service.heartbeat(OrganizationNodeHeartbeat(brain_id=worker, capabilities=["analysis"], trust_score=0.9))

    task = OrganizationTaskItem(content="Analyze bounded task", objective="produce honest evidence", requirements=["analysis"])
    session = service.announce_goal(
        OrganizationGoalAnnouncement(
            initiator_brain_id=initiator,
            title=f"G36 strike accounting {suffix}",
            risk_level="medium",
            acceptance_criteria=["evidence is genuine"],
            task_breakdown=[task],
        )
    )
    claim = service.claim_goal(
        OrganizationGoalClaim(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            claimant_brain_id=worker,
            deliverables=["analysis-note"],
            eta_seconds=60,
            time_budget_seconds=300,
        )
    )
    assert claim.status.value == "accepted"

    for index in range(3):
        submission = service.submit_completion(
            OrganizationCompletionSubmission(
                session_id=session.session_id,
                task_item_id=task.task_item_id,
                submitter_brain_id=worker,
                summary=f"fabricated completion {index}",
                evidence_refs=[],
            )
        )
        service.review_completion(
            OrganizationCompletionReview(
                submission_id=submission.submission_id,
                reviewer_brain_id=initiator,
                accepted=False,
                checklist_results={"evidence is genuine": False},
                cheating_detected=True,
                reason="review found fabricated evidence",
            )
        )

    trust = {record.brain_id: record for record in service.list_trust_records()}[worker]
    assert trust.strike_count == 3
    assert trust.banned is True
    assert trust.participation_weight == 0.0
    assert "cheating_detected" in trust.reasons
    assert "group_trust_record_banned" in {event.action for event in service.list_audit_events()}

    second_task = OrganizationTaskItem(content="Claim should be blocked", objective="blocked by trust", requirements=["analysis"])
    second_session = service.announce_goal(
        OrganizationGoalAnnouncement(
            initiator_brain_id=initiator,
            title=f"G36 banned claimant blocked {suffix}",
            risk_level="medium",
            acceptance_criteria=["blocked worker cannot participate"],
            task_breakdown=[second_task],
        )
    )
    with pytest.raises(ValueError, match="banned node"):
        service.claim_goal(
            OrganizationGoalClaim(
                session_id=second_session.session_id,
                task_item_id=second_task.task_item_id,
                claimant_brain_id=worker,
                deliverables=["should-not-enter"],
                eta_seconds=60,
                time_budget_seconds=300,
            )
        )


def test_g36_completion_gaps_claim_expiry_decline_context_forward_and_orphan_repair() -> None:
    suffix = unique_suffix()
    service = _service()
    initiator = f"g36-gap-initiator-{suffix}"
    worker = f"g36-gap-worker-{suffix}"
    recovery_owner = f"g36-gap-recovery-{suffix}"
    service.heartbeat(OrganizationNodeHeartbeat(brain_id=initiator, capabilities=["planning"], trust_score=0.95))
    service.heartbeat(OrganizationNodeHeartbeat(brain_id=worker, capabilities=["analysis"], trust_score=0.9))
    service.heartbeat(OrganizationNodeHeartbeat(brain_id=recovery_owner, capabilities=["analysis"], trust_score=0.95))

    task = OrganizationTaskItem(content="Coordinate relay work", objective="exercise remaining G36 paths", requirements=["analysis"])
    session = service.announce_goal(
        OrganizationGoalAnnouncement(
            initiator_brain_id=initiator,
            title=f"G36 missing path coverage {suffix}",
            risk_level="high",
            acceptance_criteria=["remaining protocol paths are queryable"],
            task_breakdown=[task],
            context_version=3,
        )
    )

    claim = service.claim_goal(
        OrganizationGoalClaim(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            claimant_brain_id=worker,
            deliverables=["relay-note"],
            eta_seconds=1,
            time_budget_seconds=120,
        )
    )
    expired = service.expire_pending_claims(now=datetime.now(UTC) + timedelta(seconds=2))
    assert expired[0].claim_id == claim.claim_id
    assert expired[0].status.value == "withdrawn"
    after_expiry = service.get_session(session.session_id)
    assert after_expiry.state.value == "pending"
    assert after_expiry.task_breakdown[0].status.value == "open"
    assert after_expiry.task_breakdown[0].owner_brain_id is None

    decline = service.decline_goal(
        OrganizationGoalDecline(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            brain_id=worker,
            blocked_reason="missing data access from originator",
            available_resources=["analysis"],
            blocked_resources=["source dataset"],
        )
    )
    declines = service.list_declines(session.session_id)
    assert declines[0].decline_id == decline.decline_id
    assert declines[0].blocked_resources == ["source dataset"]

    turn = service.record_conversation_turn(
        OrganizationConversationTurn(
            session_id=session.session_id,
            actor_brain_id=initiator,
            event_type="context_sync",
            payload={"context_hash": f"ctx-{suffix}"},
            context_version=3,
        )
    )
    turns = service.list_conversation_turns(session.session_id)
    assert turns[0].turn_id == turn.turn_id
    assert turns[0].payload["context_hash"] == f"ctx-{suffix}"
    with pytest.raises(ValueError, match="context_version_mismatch"):
        service.record_conversation_turn(
            OrganizationConversationTurn(
                session_id=session.session_id,
                actor_brain_id=worker,
                event_type="context_sync",
                payload={"context_hash": "stale"},
                context_version=1,
            )
        )
    assert service.list_failures(session.session_id)[-1].exception_type == OrganizationExceptionType.CONTEXT_VERSION_MISMATCH

    forward = service.forward_task(
        session_id=session.session_id,
        task_item_id=task.task_item_id,
        requester_brain_id=initiator,
        target_group_id=f"downstream-group-{suffix}",
        reason="originator confirmed no local worker can proceed",
    )
    assert forward.accepted is True
    assert service.get_session(session.session_id).forward_chain == [f"downstream-group-{suffix}"]
    with pytest.raises(ValueError, match="max_forward_depth"):
        service.forward_task(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            requester_brain_id=initiator,
            target_group_id="second-group",
            reason="second forward should be forbidden",
        )
    forwards = service.list_forwards(session.session_id)
    assert [row.accepted for row in forwards] == [True, False]

    accepted = service.claim_goal(
        OrganizationGoalClaim(
            session_id=session.session_id,
            task_item_id=task.task_item_id,
            claimant_brain_id=worker,
            deliverables=["relay-note"],
            eta_seconds=60,
            time_budget_seconds=120,
        )
    )
    service.confirm_claim(accepted.claim_id, confirmer_brain_id=initiator, accepted=True)
    service.heartbeat(OrganizationNodeHeartbeat(brain_id=worker, capabilities=["analysis"], trust_score=0.9, status="offline"))
    recovery = service.repair_orphaned_session(session_id=session.session_id, recovery_owner=recovery_owner)
    assert recovery.action == "reroute"
    assert recovery.recovery_owner == recovery_owner
    repaired = service.get_session(session.session_id)
    assert repaired.task_breakdown[0].status.value == "open"
    assert repaired.task_breakdown[0].owner_brain_id is None
    assert service.list_recoveries(session.session_id)[-1].recovery_id == recovery.recovery_id


def test_g36_api_uses_real_requests_and_checks_state_after_each_write(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.collaboration_service = _service()
    initiator = f"g36-api-initiator-{suffix}"
    worker = f"g36-api-worker-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        for brain_id, capabilities, trust in [
            (initiator, ["planning"], 0.95),
            (worker, ["python", "review"], 0.9),
        ]:
            heartbeat_response = requests.post(
                f"{base_url}/api/web/collaboration/g36/heartbeats",
                json={"brain_id": brain_id, "capabilities": capabilities, "trust_score": trust, "status": "online"},
                timeout=10,
            )
            assert heartbeat_response.status_code == 200, heartbeat_response.text
            assert heartbeat_response.json()["brain_id"] == brain_id

        goal_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/goals",
            json={
                "initiator_brain_id": initiator,
                "title": f"G36 API delegated test {suffix}",
                "risk_level": "high",
                "acceptance_criteria": ["API result is persisted and reviewed"],
                "required_evidence": ["api-test-log"],
                "task_breakdown": [
                    {
                        "content": "Run a real API delegated task",
                        "objective": "prove G36 API state transitions persist",
                        "requirements": ["python"],
                        "failure_strategy": "retryable",
                    }
                ],
                "idempotency_key": f"g36-api-{suffix}",
            },
            timeout=10,
        )
        assert goal_response.status_code == 200, goal_response.text
        session = goal_response.json()
        session_id = session["session_id"]
        task_item_id = session["task_breakdown"][0]["task_item_id"]
        assert session["security_review"]["accepted"] is True

        claim_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/claims",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "claimant_brain_id": worker,
                "deliverables": ["api-test-log"],
                "eta_seconds": 90,
                "time_budget_seconds": 300,
                "token_budget": 500,
            },
            timeout=10,
        )
        assert claim_response.status_code == 200, claim_response.text
        claim = claim_response.json()
        assert claim["status"] == "waiting_confirmation"

        query_after_claim = requests.get(f"{base_url}/api/web/collaboration/g36/goals/{session_id}", timeout=10)
        assert query_after_claim.status_code == 200, query_after_claim.text
        assert query_after_claim.json()["state"] == "waiting"
        assert query_after_claim.json()["task_breakdown"][0]["owner_brain_id"] == worker

        confirm_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/claims/{claim['claim_id']}/confirm",
            json={"confirmer_brain_id": initiator, "accepted": True},
            timeout=10,
        )
        assert confirm_response.status_code == 200, confirm_response.text
        assert confirm_response.json()["status"] == "accepted"

        progress_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/progress",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "reporter_brain_id": worker,
                "percent_complete": 100,
                "status_note": "API task completed with evidence",
                "evidence_refs": ["api-test-log"],
            },
            timeout=10,
        )
        assert progress_response.status_code == 200, progress_response.text
        assert progress_response.json()["percent_complete"] == 100

        completion_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/completions",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "submitter_brain_id": worker,
                "summary": "API completion carries required evidence",
                "evidence_refs": ["api-test-log"],
                "result_payload": {"api_suffix": suffix, "persisted": True},
            },
            timeout=10,
        )
        assert completion_response.status_code == 200, completion_response.text
        submission = completion_response.json()
        assert submission["result_payload"]["api_suffix"] == suffix

        review_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/reviews",
            json={
                "submission_id": submission["submission_id"],
                "reviewer_brain_id": initiator,
                "accepted": True,
                "checklist_results": {"API result is persisted and reviewed": True},
                "cheating_detected": False,
                "reason": "requests-based API test queried the persisted session after each write",
            },
            timeout=10,
        )
        assert review_response.status_code == 200, review_response.text
        assert review_response.json()["accepted"] is True

        final_query = requests.get(f"{base_url}/api/web/collaboration/g36/goals/{session_id}", timeout=10)
        audit_query = requests.get(f"{base_url}/api/web/collaboration/g36/audit", params={"session_id": session_id}, timeout=10)
        outcome_query = requests.get(f"{base_url}/api/web/collaboration/g36/outcomes", params={"session_id": session_id}, timeout=10)

    assert final_query.status_code == 200, final_query.text
    final_session = final_query.json()
    assert final_session["state"] == "completed"
    assert final_session["final_ack"] is True
    assert final_session["memory_write_gate"] is True
    assert final_session["audit_closeout"] is True
    assert final_session["task_breakdown"][0]["status"] == "completed"
    assert final_session["task_breakdown"][0]["owner_brain_id"] == worker

    assert audit_query.status_code == 200, audit_query.text
    audit_actions = {row["action"] for row in audit_query.json()}
    assert {"goal_announcement", "goal_claim", "goal_progress", "goal_completion_submission", "goal_completion_review"}.issubset(audit_actions)

    assert outcome_query.status_code == 200, outcome_query.text
    outcomes = outcome_query.json()
    assert outcomes[0]["success"] is True
    assert "memory_write_gate" in outcomes[0]["next_actions"]


def test_g36_gap_api_uses_requests_for_decline_context_forward_expire_and_orphan_repair(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.collaboration_service = _service()
    initiator = f"g36-gap-api-initiator-{suffix}"
    worker = f"g36-gap-api-worker-{suffix}"
    recovery_owner = f"g36-gap-api-recovery-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        for brain_id, capabilities, status in [
            (initiator, ["planning"], "online"),
            (worker, ["analysis"], "online"),
            (recovery_owner, ["analysis"], "online"),
        ]:
            heartbeat_response = requests.post(
                f"{base_url}/api/web/collaboration/g36/heartbeats",
                json={"brain_id": brain_id, "capabilities": capabilities, "trust_score": 0.95, "status": status},
                timeout=10,
            )
            assert heartbeat_response.status_code == 200, heartbeat_response.text

        goal_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/goals",
            json={
                "initiator_brain_id": initiator,
                "title": f"G36 gap API session {suffix}",
                "risk_level": "high",
                "acceptance_criteria": ["gap endpoints are real"],
                "context_version": 2,
                "task_breakdown": [
                    {
                        "content": "Exercise gap endpoints",
                        "objective": "query each mutation after write",
                        "requirements": ["analysis"],
                    }
                ],
            },
            timeout=10,
        )
        assert goal_response.status_code == 200, goal_response.text
        session = goal_response.json()
        session_id = session["session_id"]
        task_item_id = session["task_breakdown"][0]["task_item_id"]

        decline_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/declines",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "brain_id": worker,
                "blocked_reason": "missing source material",
                "available_resources": ["analysis"],
                "blocked_resources": ["source material"],
            },
            timeout=10,
        )
        assert decline_response.status_code == 200, decline_response.text
        declines_query = requests.get(f"{base_url}/api/web/collaboration/g36/declines", params={"session_id": session_id}, timeout=10)
        assert declines_query.status_code == 200, declines_query.text
        assert declines_query.json()[0]["blocked_resources"] == ["source material"]

        turn_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/conversation-turns",
            json={
                "session_id": session_id,
                "actor_brain_id": initiator,
                "event_type": "context_sync",
                "payload": {"context_hash": f"api-context-{suffix}"},
                "context_version": 2,
            },
            timeout=10,
        )
        assert turn_response.status_code == 200, turn_response.text
        stale_turn = requests.post(
            f"{base_url}/api/web/collaboration/g36/conversation-turns",
            json={
                "session_id": session_id,
                "actor_brain_id": worker,
                "event_type": "context_sync",
                "payload": {"context_hash": "stale"},
                "context_version": 1,
            },
            timeout=10,
        )
        assert stale_turn.status_code == 409
        turn_query = requests.get(f"{base_url}/api/web/collaboration/g36/conversation-turns", params={"session_id": session_id}, timeout=10)
        failure_query = requests.get(f"{base_url}/api/web/collaboration/g36/failures", params={"session_id": session_id}, timeout=10)
        assert turn_query.status_code == 200, turn_query.text
        assert turn_query.json()[0]["payload"]["context_hash"] == f"api-context-{suffix}"
        assert failure_query.status_code == 200, failure_query.text
        assert failure_query.json()[-1]["exception_type"] == "context_version_mismatch"

        forward_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/forwards",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "requester_brain_id": initiator,
                "target_group_id": f"api-downstream-{suffix}",
                "reason": "no local worker can proceed with missing source",
            },
            timeout=10,
        )
        assert forward_response.status_code == 200, forward_response.text
        second_forward = requests.post(
            f"{base_url}/api/web/collaboration/g36/forwards",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "requester_brain_id": initiator,
                "target_group_id": "second-hop",
                "reason": "must be blocked",
            },
            timeout=10,
        )
        assert second_forward.status_code == 409
        forwards_query = requests.get(f"{base_url}/api/web/collaboration/g36/forwards", params={"session_id": session_id}, timeout=10)
        assert forwards_query.status_code == 200, forwards_query.text
        assert [row["accepted"] for row in forwards_query.json()] == [True, False]

        claim_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/claims",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "claimant_brain_id": worker,
                "deliverables": ["analysis note"],
                "eta_seconds": 1,
                "time_budget_seconds": 120,
            },
            timeout=10,
        )
        assert claim_response.status_code == 200, claim_response.text
        time.sleep(1.1)
        expire_response = requests.post(f"{base_url}/api/web/collaboration/g36/claims/expire", timeout=10)
        assert expire_response.status_code == 200, expire_response.text
        assert expire_response.json()[0]["status"] == "withdrawn"
        after_expire = requests.get(f"{base_url}/api/web/collaboration/g36/goals/{session_id}", timeout=10)
        assert after_expire.status_code == 200, after_expire.text
        assert after_expire.json()["task_breakdown"][0]["status"] == "open"
        assert after_expire.json()["task_breakdown"][0]["owner_brain_id"] is None

        second_claim = requests.post(
            f"{base_url}/api/web/collaboration/g36/claims",
            json={
                "session_id": session_id,
                "task_item_id": task_item_id,
                "claimant_brain_id": worker,
                "deliverables": ["analysis note"],
                "eta_seconds": 60,
                "time_budget_seconds": 120,
            },
            timeout=10,
        )
        assert second_claim.status_code == 200, second_claim.text
        confirm_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/claims/{second_claim.json()['claim_id']}/confirm",
            json={"confirmer_brain_id": initiator, "accepted": True},
            timeout=10,
        )
        assert confirm_response.status_code == 200, confirm_response.text
        offline_worker = requests.post(
            f"{base_url}/api/web/collaboration/g36/heartbeats",
            json={"brain_id": worker, "capabilities": ["analysis"], "trust_score": 0.95, "status": "offline"},
            timeout=10,
        )
        assert offline_worker.status_code == 200, offline_worker.text
        repair_response = requests.post(
            f"{base_url}/api/web/collaboration/g36/orphaned-session-repairs",
            json={"session_id": session_id, "recovery_owner": recovery_owner},
            timeout=10,
        )
        assert repair_response.status_code == 200, repair_response.text
        recoveries_query = requests.get(f"{base_url}/api/web/collaboration/g36/recoveries", params={"session_id": session_id}, timeout=10)
        repaired_session = requests.get(f"{base_url}/api/web/collaboration/g36/goals/{session_id}", timeout=10)

    assert recoveries_query.status_code == 200, recoveries_query.text
    assert recoveries_query.json()[-1]["action"] == "reroute"
    assert recoveries_query.json()[-1]["recovery_owner"] == recovery_owner
    assert repaired_session.status_code == 200, repaired_session.text
    assert repaired_session.json()["task_breakdown"][0]["status"] == "open"
    assert repaired_session.json()["task_breakdown"][0]["owner_brain_id"] is None
