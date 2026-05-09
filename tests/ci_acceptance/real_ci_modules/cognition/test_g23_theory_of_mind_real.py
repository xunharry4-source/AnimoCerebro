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
from zentex.cognition.theory_of_mind import EntityType, InteractionSignal, SignalType, TheoryOfMindEngine


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


def test_g23_observation_builds_queryable_mind_model_and_blocks_unconfirmed_high_risk_intent() -> None:
    suffix = unique_suffix()
    entity_id = f"g23-user-{suffix}"
    engine = TheoryOfMindEngine()

    model = engine.observe_entity(
        entity_id=entity_id,
        entity_type=EntityType.USER,
        signals=[
            InteractionSignal(
                entity_id=entity_id,
                signal_type=SignalType.STATEMENT,
                content="I can follow Python test code but need Kubernetes explained slowly.",
                topics=["python-testing"],
                evidence_refs=[f"transcript://{suffix}/statement"],
                metadata={
                    "known_topics": ["python-testing", "pytest"],
                    "missing_topics": ["kubernetes-rollout"],
                    "knowledge_depth": "working",
                    "tolerance_for_detail": "low",
                },
            ),
            InteractionSignal(
                entity_id=entity_id,
                signal_type=SignalType.HIGH_RISK_SIGNAL,
                content="Maybe delete the production namespace to recover faster.",
                risk_markers=["destructive_change", "production"],
                evidence_refs=[f"transcript://{suffix}/risk"],
                metadata={"intent": "delete production namespace immediately", "confidence": 0.78},
            ),
        ],
    )
    queried = engine.get_mind_model(entity_id)

    assert queried is not None
    assert queried.entity_id == entity_id
    assert queried.knowledge_depth == "working"
    assert queried.tolerance_for_detail == "low"
    assert queried.knowledge_boundary.known_topics == ["pytest", "python-testing"]
    assert queried.knowledge_boundary.likely_missing_topics == ["kubernetes-rollout"]
    assert queried.current_interaction_state == "confirming"
    assert len(queried.active_hypotheses) == 1
    hypothesis = queried.active_hypotheses[0]
    assert hypothesis.status == "hypothesis"
    assert hypothesis.content == "delete production namespace immediately"
    assert hypothesis.high_risk is True
    assert hypothesis.requires_g19_confirmation is True
    assert hypothesis.allowed_to_drive_high_risk_action is False
    assert queried.recommended_strategy.collaboration_mode == "confirm_first"
    assert queried.recommended_strategy.rationale == "high_risk_intent_hypothesis_requires_g19_confirmation"
    assert model.revision == queried.revision


def test_g23_feedback_correction_rejects_wrong_hypothesis_and_persists_confirmed_intent() -> None:
    suffix = unique_suffix()
    entity_id = f"g23-agent-{suffix}"
    engine = TheoryOfMindEngine()
    model = engine.observe_entity(
        entity_id=entity_id,
        entity_type=EntityType.AGENT,
        signals=[
            InteractionSignal(
                entity_id=entity_id,
                signal_type=SignalType.INTENT_SIGNAL,
                content="Agent asks for broad repository write access.",
                topics=["repo-write"],
                evidence_refs=[f"agent://{suffix}/proposal"],
                metadata={"intent": "obtain broad repository write access", "knowledge_depth": "expert"},
            )
        ],
    )
    wrong = model.active_hypotheses[0]

    corrected = engine.record_correction(
        entity_id=entity_id,
        hypothesis_id=wrong.hypothesis_id,
        corrected_intent="request read-only inspection scope",
        evidence_ref=f"agent://{suffix}/correction",
        confirmed=True,
    )
    queried = engine.get_mind_model(entity_id)

    assert queried is not None
    assert queried.revision == corrected.revision
    assert all(item.hypothesis_id != wrong.hypothesis_id for item in queried.active_hypotheses)
    assert len(queried.correction_history) == 1
    assert queried.correction_history[0].rejected_hypothesis_id == wrong.hypothesis_id
    assert queried.correction_history[0].corrected_intent == "request read-only inspection scope"
    assert queried.confirmed_intents[-1].content == "request read-only inspection scope"
    assert queried.confirmed_intents[-1].status == "confirmed"
    assert queried.current_interaction_state == "collaborating"


def test_g23_confirmed_high_risk_intent_still_requires_g19_confirmation_and_cannot_drive_action() -> None:
    suffix = unique_suffix()
    entity_id = f"g23-confirmed-risk-{suffix}"
    engine = TheoryOfMindEngine()

    model = engine.observe_entity(
        entity_id=entity_id,
        entity_type=EntityType.USER,
        signals=[
            InteractionSignal(
                entity_id=entity_id,
                signal_type=SignalType.CONFIRMATION,
                content="I explicitly want the credential rotation to skip external confirmation.",
                risk_markers=["credential", "confirmation_bypass"],
                evidence_refs=[f"transcript://{suffix}/confirmed-risk"],
                metadata={
                    "confirmed_intent": "skip external confirmation for credential rotation",
                    "known_topics": ["credential-rotation"],
                    "knowledge_depth": "expert",
                    "tolerance_for_detail": "high",
                },
            )
        ],
    )
    queried = engine.get_mind_model(entity_id)

    assert queried is not None
    assert queried.revision == model.revision
    assert queried.active_hypotheses == []
    assert len(queried.confirmed_intents) == 1
    confirmed = queried.confirmed_intents[0]
    assert confirmed.status == "confirmed"
    assert confirmed.high_risk is True
    assert confirmed.requires_g19_confirmation is True
    assert confirmed.allowed_to_drive_high_risk_action is False
    assert queried.current_interaction_state == "confirming"
    assert queried.recommended_strategy.collaboration_mode == "confirm_first"
    assert queried.recommended_strategy.rationale == "high_risk_intent_hypothesis_requires_g19_confirmation"


def test_g23_theory_of_mind_api_uses_requests_and_read_after_write_checks_model_and_correction(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    entity_id = f"g23-api-user-{suffix}"
    acceptance_app.state.theory_of_mind_engine = TheoryOfMindEngine()

    with _live_http_server(acceptance_app) as base_url:
        observe_response = requests.post(
            f"{base_url}/api/web/theory-of-mind/entities/{entity_id}/observations",
            json={
                "entity_type": "user",
                "signals": [
                    {
                        "entity_id": entity_id,
                        "signal_type": "statement",
                        "content": "I know FastAPI but not cloud audit rollout.",
                        "topics": ["fastapi"],
                        "evidence_refs": [f"transcript://{suffix}/api-statement"],
                        "metadata": {
                            "known_topics": ["fastapi"],
                            "missing_topics": ["cloud-audit-rollout"],
                            "knowledge_depth": "working",
                            "tolerance_for_detail": "medium",
                        },
                    },
                    {
                        "entity_id": entity_id,
                        "signal_type": "high_risk_signal",
                        "content": "Skip confirmation for credential rotation.",
                        "risk_markers": ["credential", "confirmation_bypass"],
                        "evidence_refs": [f"transcript://{suffix}/api-risk"],
                        "metadata": {"intent": "skip confirmation for credential rotation"},
                    },
                ],
            },
            timeout=10,
        )
        assert observe_response.status_code == 200
        observed = observe_response.json()
        hypothesis_id = observed["active_hypotheses"][0]["hypothesis_id"]

        read_response = requests.get(f"{base_url}/api/web/theory-of-mind/entities/{entity_id}", timeout=10)
        correction_response = requests.post(
            f"{base_url}/api/web/theory-of-mind/entities/{entity_id}/corrections",
            json={
                "hypothesis_id": hypothesis_id,
                "corrected_intent": "ask for a supervised credential rotation checklist",
                "evidence_ref": f"transcript://{suffix}/api-correction",
                "confirmed": True,
            },
            timeout=10,
        )
        final_response = requests.get(f"{base_url}/api/web/theory-of-mind/entities/{entity_id}", timeout=10)

    assert read_response.status_code == 200
    read_model = read_response.json()
    assert read_model["knowledge_boundary"]["known_topics"] == ["fastapi"]
    assert read_model["knowledge_boundary"]["likely_missing_topics"] == ["cloud-audit-rollout"]
    assert read_model["active_hypotheses"][0]["requires_g19_confirmation"] is True
    assert read_model["active_hypotheses"][0]["allowed_to_drive_high_risk_action"] is False
    assert read_model["recommended_strategy"]["collaboration_mode"] == "confirm_first"

    assert correction_response.status_code == 200
    corrected = correction_response.json()
    assert corrected["active_hypotheses"] == []
    assert corrected["confirmed_intents"][-1]["content"] == "ask for a supervised credential rotation checklist"
    assert corrected["correction_history"][0]["rejected_hypothesis_id"] == hypothesis_id

    assert final_response.status_code == 200
    final_model = final_response.json()
    assert final_model["revision"] == corrected["revision"]
    assert final_model["confirmed_intents"][-1]["status"] == "confirmed"
    assert final_model["current_interaction_state"] == "collaborating"
