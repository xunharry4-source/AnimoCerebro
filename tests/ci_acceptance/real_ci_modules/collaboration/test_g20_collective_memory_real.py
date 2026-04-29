from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import socket
import threading
import time

import requests
import uvicorn
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.collaboration.collective_memory import CollectiveMemory
from zentex.collaboration.models import PeerBrain, VoteDecision
from zentex.collaboration.service import CollaborationService
from zentex.web_console.router import api_router


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


def test_g20_shared_experience_verifies_signature_and_quarantines_low_trust_source() -> None:
    suffix = unique_suffix()
    local = CollaborationService(CollectiveMemory(local_brain_id=f"local-{suffix}", local_secret=f"local-secret-{suffix}"))
    remote_brain_id = f"remote-low-trust-{suffix}"
    remote_secret = f"remote-secret-{suffix}"
    local.register_peer(PeerBrain(brain_id=remote_brain_id, shared_secret=remote_secret, trust_score=0.2))

    remote = CollectiveMemory(local_brain_id=remote_brain_id, local_secret=remote_secret)
    outbound = remote.create_shared_experience(
        {
            "lesson": "remote failure pattern must be quarantined before adoption",
            "source_trace_id": f"trace-g20-{suffix}",
        }
    )
    received = local.receive_shared_experience(outbound)
    queried = local.get_shared_experience(received.experience_id)

    assert queried is not None
    assert queried.experience_id == outbound.experience_id
    assert queried.accepted_to_core_memory is False
    assert queried.quarantine_reason == "source trust below core-memory threshold or inactive"
    assert queried.payload["source_trace_id"] == f"trace-g20-{suffix}"


def test_g20_high_risk_consensus_cannot_pass_until_quorum_is_reached() -> None:
    suffix = unique_suffix()
    service = CollaborationService(CollectiveMemory(local_brain_id=f"local-{suffix}", local_secret=f"local-secret-{suffix}"))
    peer_a = PeerBrain(brain_id=f"peer-a-{suffix}", shared_secret=f"peer-a-secret-{suffix}")
    peer_b = PeerBrain(brain_id=f"peer-b-{suffix}", shared_secret=f"peer-b-secret-{suffix}")
    service.register_peer(peer_a)
    service.register_peer(peer_b)

    proposal = service.create_consensus_proposal(
        topic="approve high risk execution only after quorum",
        payload={"risk": "critical", "action": "self_modify"},
        quorum=2,
        risk_level="critical",
    )
    first = service.submit_vote(
        proposal_id=proposal.proposal_id,
        voter_brain_id=peer_a.brain_id,
        decision=VoteDecision.APPROVE,
        rationale="evidence reviewed by peer A",
    )
    assert first.status.value == "pending"
    assert first.passed is False

    second = service.submit_vote(
        proposal_id=proposal.proposal_id,
        voter_brain_id=peer_b.brain_id,
        decision=VoteDecision.APPROVE,
        rationale="evidence reviewed by peer B",
    )
    queried = service.get_consensus_proposal(proposal.proposal_id)
    assert queried is not None
    assert second.status.value == "passed"
    assert queried.passed is True


def test_g20_collaboration_api_uses_real_requests_and_preserves_failed_ack(acceptance_app: FastAPI) -> None:
    suffix = unique_suffix()
    acceptance_app.state.collaboration_service = CollaborationService(
        CollectiveMemory(local_brain_id=f"api-local-{suffix}", local_secret=f"api-local-secret-{suffix}")
    )
    target_brain_id = f"api-peer-no-mailbox-{suffix}"

    with _live_http_server(acceptance_app) as base_url:
        peer_response = requests.post(
            f"{base_url}/api/web/collaboration/peers",
            json={
                "brain_id": target_brain_id,
                "shared_secret": f"api-peer-secret-{suffix}",
                "trust_score": 1.0,
                "active": True,
            },
            timeout=10,
        )
        assert peer_response.status_code == 200

        create_response = requests.post(
            f"{base_url}/api/web/collaboration/experiences",
            json={
                "payload": {"lesson": "failed mailbox delivery must remain auditable", "suffix": suffix},
                "target_brain_ids": [target_brain_id],
                "transport_mode": "mailbox",
            },
            timeout=10,
        )
        assert create_response.status_code == 200
        created = create_response.json()
        experience_id = created["experience"]["experience_id"]
        assert created["experience"]["accepted_to_core_memory"] is True
        assert created["acks"][0]["status"] == "failed"
        assert created["acks"][0]["target_brain_id"] == target_brain_id
        assert "Mailbox handler" in created["acks"][0]["error"]

        query_response = requests.get(f"{base_url}/api/web/collaboration/experiences/{experience_id}", timeout=10)
        ack_response = requests.get(f"{base_url}/api/web/collaboration/acks/{experience_id}", timeout=10)

    assert query_response.status_code == 200
    assert query_response.json()["payload"]["suffix"] == suffix
    assert ack_response.status_code == 200
    assert ack_response.json()[0]["status"] == "failed"


def test_g20_collaboration_api_uses_real_http_transport_and_remote_read_after_write() -> None:
    suffix = unique_suffix()
    local_brain_id = f"http-local-{suffix}"
    local_secret = f"http-local-secret-{suffix}"
    remote_brain_id = f"http-remote-{suffix}"
    remote_secret = f"http-remote-secret-{suffix}"

    local_app = FastAPI()
    local_app.include_router(api_router)
    local_app.state.collaboration_service = CollaborationService(
        CollectiveMemory(local_brain_id=local_brain_id, local_secret=local_secret)
    )

    remote_app = FastAPI()
    remote_app.include_router(api_router)
    remote_service = CollaborationService(
        CollectiveMemory(local_brain_id=remote_brain_id, local_secret=remote_secret)
    )
    remote_service.register_peer(PeerBrain(brain_id=local_brain_id, shared_secret=local_secret, trust_score=1.0))
    remote_app.state.collaboration_service = remote_service

    with _live_http_server(remote_app) as remote_url, _live_http_server(local_app) as local_url:
        peer_response = requests.post(
            f"{local_url}/api/web/collaboration/peers",
            json={
                "brain_id": remote_brain_id,
                "shared_secret": remote_secret,
                "endpoint": remote_url,
                "trust_score": 1.0,
                "active": True,
            },
            timeout=10,
        )
        assert peer_response.status_code == 200, peer_response.text

        create_response = requests.post(
            f"{local_url}/api/web/collaboration/experiences",
            json={
                "payload": {
                    "lesson": "http transport must persist the exact shared experience remotely",
                    "suffix": suffix,
                },
                "target_brain_ids": [remote_brain_id],
                "transport_mode": "http",
            },
            timeout=10,
        )
        assert create_response.status_code == 200, create_response.text
        created = create_response.json()
        experience_id = created["experience"]["experience_id"]
        assert created["acks"][0]["status"] == "delivered"
        assert created["acks"][0]["transport_mode"] == "http"
        assert created["acks"][0]["error"] is None

        remote_query_response = requests.get(
            f"{remote_url}/api/web/collaboration/experiences/{experience_id}",
            timeout=10,
        )
        local_ack_response = requests.get(
            f"{local_url}/api/web/collaboration/acks/{experience_id}",
            timeout=10,
        )

    assert remote_query_response.status_code == 200, remote_query_response.text
    remote_experience = remote_query_response.json()
    assert remote_experience["source_brain_id"] == local_brain_id
    assert remote_experience["payload"]["suffix"] == suffix
    assert remote_experience["accepted_to_core_memory"] is True
    assert local_ack_response.status_code == 200, local_ack_response.text
    assert local_ack_response.json()[0]["status"] == "delivered"
