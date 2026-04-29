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
from zentex.safety.sanity_auditor import SanityAuditor


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


def test_g25_clean_audit_is_queryable_and_allows_self_modification_after_checkpoint() -> None:
    suffix = unique_suffix()
    auditor = SanityAuditor(brain_scope=f"g25-clean-{suffix}")
    auditor.set_baseline_profile({"curiosity": 0.4, "safety": 0.8, "mission_focus": 0.9})
    checkpoint = auditor.create_checkpoint({"snapshot": suffix, "strategy_version": 1})

    report = auditor.audit(
        world_model={
            "active_goals": [{"id": "goal-a", "name": "document current module", "priority": 1}],
            "physical_host_state": {"network": {"status": "connected"}, "memory": {"status": "normal"}},
            "external_signals": [],
        },
        strategy_graph={
            "policies": {"policy-a": {"action": "inspect", "conditions": ["read_only"]}},
            "actions": ["inspect"],
            "reasoning_chains": [{"path": ["observe", "plan", "verify"]}],
        },
        ban_layer={"banned_actions": ["delete_file"]},
        motivation_state={"curiosity": 0.4, "safety": 0.8, "mission_focus": 0.9},
    )
    queried = auditor.get_audit(report.audit_id)
    checkpoints = auditor.list_checkpoints()

    assert queried is not None
    assert queried.status == "passed"
    assert queried.disposition == "continue"
    assert queried.g18_self_shaping_blocked is False
    assert queried.recommended_actions == ["continue"]
    assert queried.rollback_checkpoint_id == checkpoint.checkpoint_id
    assert len(auditor.list_audits()) == 1
    assert checkpoints[0].checkpoint_id == checkpoint.checkpoint_id
    auditor.assert_self_modification_allowed(audit_id=report.audit_id)


def test_g25_conflict_loop_and_motivation_drift_block_g18_and_are_queryable() -> None:
    suffix = unique_suffix()
    auditor = SanityAuditor(brain_scope=f"g25-failed-{suffix}", drift_threshold=0.2, loop_recurrence_threshold=3)
    auditor.set_baseline_profile({"curiosity": 0.2, "safety": 0.9, "mission_focus": 0.9})
    checkpoint = auditor.create_checkpoint({"snapshot": suffix, "strategy_version": 7})

    report = auditor.audit(
        world_model={
            "active_goals": [
                {
                    "id": "ship-risky",
                    "name": "ship risky change",
                    "priority": 5,
                    "required_resources": ["runtime"],
                    "target_outcome": "deploy",
                },
                {
                    "id": "block-risky",
                    "name": "block risky change",
                    "priority": 5,
                    "required_resources": ["runtime"],
                    "target_outcome": "!deploy",
                },
            ],
            "physical_host_state": {"network": {"status": "connected"}, "memory": {"status": "normal"}},
            "external_signals": [],
        },
        strategy_graph={
            "policies": {
                "prefer-deploy": {"action": "deploy", "conditions": ["high_uncertainty"]},
                "forbid-deploy": {"action": "!deploy", "conditions": ["high_uncertainty"]},
            },
            "actions": ["deploy", "self_modify"],
            "reasoning_chains": [{"path": ["assume", "patch", "assume", "patch", "assume"]}],
        },
        ban_layer={"banned_actions": ["self_modify"]},
        motivation_state={"curiosity": 0.95, "safety": 0.2, "mission_focus": 0.1},
    )

    assert report.status == "failed"
    assert report.disposition == "human_review"
    assert report.g18_self_shaping_blocked is True
    assert report.rollback_checkpoint_id == checkpoint.checkpoint_id
    assert "block_self_mod" in [action.value for action in report.recommended_actions]
    assert "rollback" in [action.value for action in report.recommended_actions]
    assert len(report.belief_conflicts) == 3
    assert any(conflict.conflict_type == "rule" for conflict in report.belief_conflicts)
    assert len(report.reasoning_loops) == 1
    assert report.reasoning_loops[0].truncation_point == "assume"
    assert len(report.motivation_drifts) == 1
    assert set(report.motivation_drifts[0].drift_dimensions) == {"curiosity", "safety", "mission_focus"}
    with pytest.raises(RuntimeError, match="G18 self-shaping blocked"):
        auditor.assert_self_modification_allowed(audit_id=report.audit_id)
    assert auditor.get_checkpoint(checkpoint.checkpoint_id).brain_state["strategy_version"] == 7


def test_g25_external_signal_conflict_freezes_and_requires_human_review() -> None:
    suffix = unique_suffix()
    auditor = SanityAuditor(brain_scope=f"g25-external-{suffix}")
    auditor.set_baseline_profile({"curiosity": 0.4, "safety": 0.8})

    report = auditor.audit(
        world_model={
            "active_goals": [],
            "physical_host_state": {"network": {"status": "connected"}, "memory": {"status": "normal"}},
            "external_signals": [
                {
                    "source": f"host-signal-{suffix}",
                    "content": {"network_status": "disconnected", "memory_status": "critical"},
                }
            ],
        },
        strategy_graph={"policies": {}, "actions": [], "reasoning_chains": []},
        ban_layer={"banned_actions": []},
        motivation_state={"curiosity": 0.4, "safety": 0.8},
    )

    assert report.status == "frozen"
    assert report.disposition == "freeze"
    assert report.g18_self_shaping_blocked is True
    assert len(report.external_conflicts) == 1
    assert report.external_conflicts[0].signal_source == f"host-signal-{suffix}"
    assert "network disconnected" in report.external_conflicts[0].conflict_description
    assert "human_review" in [action.value for action in report.recommended_actions]


def test_g25_sanity_auditor_api_uses_requests_and_read_after_write_checks_audit_and_gate(
    acceptance_app: FastAPI,
) -> None:
    suffix = unique_suffix()
    acceptance_app.state.sanity_auditor = SanityAuditor(brain_scope=f"g25-api-{suffix}", drift_threshold=0.2)

    with _live_http_server(acceptance_app) as base_url:
        baseline_response = requests.post(
            f"{base_url}/api/web/sanity-auditor/baseline",
            json={"profile": {"curiosity": 0.3, "safety": 0.9, "mission_focus": 0.9}},
            timeout=10,
        )
        checkpoint_response = requests.post(
            f"{base_url}/api/web/sanity-auditor/checkpoints",
            json={"brain_state": {"snapshot": suffix, "strategy_version": 3}},
            timeout=10,
        )
        assert baseline_response.status_code == 200
        assert checkpoint_response.status_code == 200
        checkpoint = checkpoint_response.json()

        audit_response = requests.post(
            f"{base_url}/api/web/sanity-auditor/audits",
            json={
                "world_model": {
                    "active_goals": [],
                    "physical_host_state": {"network": {"status": "connected"}, "memory": {"status": "normal"}},
                    "external_signals": [
                        {
                            "source": f"api-signal-{suffix}",
                            "content": {"network_status": "disconnected"},
                        }
                    ],
                },
                "strategy_graph": {
                    "policies": {
                        "allow": {"action": "execute", "conditions": ["same_context"]},
                        "deny": {"action": "!execute", "conditions": ["same_context"]},
                    },
                    "actions": ["self_modify"],
                    "reasoning_chains": [{"path": ["x", "y", "x", "y", "x"]}],
                },
                "ban_layer": {"banned_actions": ["self_modify"]},
                "motivation_state": {"curiosity": 0.9, "safety": 0.2, "mission_focus": 0.1},
                "self_rewrite_history": [{"change_id": suffix, "action": "candidate_patch"}],
            },
            timeout=10,
        )
        assert audit_response.status_code == 200
        audit = audit_response.json()
        audit_id = audit["audit_id"]
        get_response = requests.get(f"{base_url}/api/web/sanity-auditor/audits/{audit_id}", timeout=10)
        list_response = requests.get(f"{base_url}/api/web/sanity-auditor/audits", timeout=10)
        gate_response = requests.get(
            f"{base_url}/api/web/sanity-auditor/audits/{audit_id}/self-modification-gate",
            timeout=10,
        )
        checkpoint_get_response = requests.get(
            f"{base_url}/api/web/sanity-auditor/checkpoints/{checkpoint['checkpoint_id']}",
            timeout=10,
        )

    assert get_response.status_code == 200
    queried = get_response.json()
    assert queried["audit_id"] == audit_id
    assert queried["status"] == "frozen"
    assert queried["disposition"] == "freeze"
    assert queried["g18_self_shaping_blocked"] is True
    assert queried["rollback_checkpoint_id"] == checkpoint["checkpoint_id"]
    assert len(queried["belief_conflicts"]) == 2
    assert queried["belief_conflicts"][1]["conflict_type"] == "rule"
    assert len(queried["reasoning_loops"]) == 1
    assert queried["reasoning_loops"][0]["truncation_point"] == "x"
    assert len(queried["motivation_drifts"]) == 1
    assert len(queried["external_conflicts"]) == 1
    assert queried["external_conflicts"][0]["signal_source"] == f"api-signal-{suffix}"

    assert list_response.status_code == 200
    assert [row["audit_id"] for row in list_response.json()] == [audit_id]
    assert gate_response.status_code == 200
    gate = gate_response.json()
    assert gate["audit_id"] == audit_id
    assert gate["g18_self_shaping_allowed"] is False
    assert gate["g18_self_shaping_blocked"] is True
    assert "block_self_mod" in gate["recommended_actions"]
    assert "human_review" in gate["recommended_actions"]
    assert checkpoint_get_response.status_code == 200
    assert checkpoint_get_response.json()["brain_state"]["strategy_version"] == 3
