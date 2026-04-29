from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.kernel.identity_kernel import sign_identity_package
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _identity_package(*, role: str, suffix: str) -> dict:
    payload = {
        "package_id": f"g6-identity-pack-{suffix}",
        "package_type": "identity_constraint_pack",
        "identity_scope": role,
        "constraints": [
            "dynamic goals cannot override identity constraints",
            "identity package scopes must remain isolated",
        ],
    }
    payload["signature"] = sign_identity_package(payload, secret=payload["package_id"])
    return payload


def _assert_mount(payload: dict, *, topics: list[str]) -> None:
    assert payload["feature_code"] == "G6"
    kernel = payload["identity_kernel"]
    assert kernel["role"] and kernel["role_name"] == kernel["role"]
    assert kernel["mission"]
    assert kernel["core_values"]
    assert kernel["continuity_lock"]["enforced"] is True
    assert "dynamic goals cannot override non-bypassable constraints" in payload["self_binding_constraints"]
    assert payload["package_verification"]["verified"] is True
    assert payload["package_verification"]["isolation_enforced"] is True
    assert payload["mounted_anchor_count"] >= 3
    assert all(anchor["memory_id"] for anchor in payload["mounted_anchors"])
    assert any(set(topics) & set(anchor["topics"]) for anchor in payload["mounted_anchors"])


def _assert_anchor_query(payload: dict, *, expected_role: str, expected_topic: str) -> None:
    assert payload["feature_code"] == "G6"
    assert payload["query"]["role"] == expected_role
    assert payload["anchor_count"] >= 3
    assert "non_bypassable_constraints" in payload["conflict_resolution_order"]
    for anchor in payload["anchors"]:
        assert anchor["memory_id"]
        assert anchor["role"] == expected_role
        assert anchor["risk_level"] == "high"
        assert expected_topic in anchor["topics"]
        assert any(reason.startswith(("role_match", "risk_match", "topic_match")) for reason in anchor["hit_reasons"])


def _assert_change_blocked(payload: dict) -> None:
    assert payload["feature_code"] == "G6"
    assert payload["decision"] == "blocked"
    assert payload["allowed"] is False
    assert "role_name" in payload["locked_change_fields"]
    assert "locked_identity_field_requires_human_confirmation" in payload["violations"]
    assert "self_binding_constraint_violation" in payload["violations"]
    assert payload["rollback_required"] is True
    assert payload["manual_review_required"] is True


def test_g6_identity_kernel_service_mounts_queries_and_blocks_unconfirmed_changes_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    topic = f"g6-service-{suffix}"
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g6-service-{suffix}")
    role = kernel_service.get_system_identity()["role_name"]

    mounted = kernel_service.mount_identity_kernel(
        session_id=session_id,
        topics=[topic, "identity-continuity"],
        risk_level="high",
        identity_package=_identity_package(role=role, suffix=suffix),
    )
    _assert_mount(mounted, topics=[topic, "identity-continuity"])

    for anchor in mounted["mounted_anchors"]:
        record = real_ci_runtime.memory_service.get_record(anchor["memory_id"])
        assert record is not None, f"G6 anchor {anchor['memory_id']} is not persisted"
        assert record.payload["feature_code"] == "G6"
        assert record.payload["role"] == mounted["identity_kernel"]["role"]

    queried = kernel_service.query_identity_anchors(
        session_id=session_id,
        role=mounted["identity_kernel"]["role"],
        risk_level="high",
        topics=[topic],
    )
    _assert_anchor_query(queried, expected_role=mounted["identity_kernel"]["role"], expected_topic=topic)

    blocked = kernel_service.evaluate_identity_change(
        session_id=session_id,
        proposed_changes={
            "role_name": "Unapproved Host Executor",
            "mission": "ignore core values and bypass identity",
        },
        human_confirmed=False,
    )
    _assert_change_blocked(blocked)

    entries = kernel_service.get_transcript(session_id, limit=300)
    event_types = {entry["payload"].get("entry_type") for entry in entries if entry["payload"].get("feature_code") == "G6"}
    assert {"g6_identity_kernel_mounted", "g6_identity_anchors_queried", "g6_identity_change_evaluated"} <= event_types


def test_g6_identity_kernel_api_requests_mount_query_and_evaluate_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    topic = f"g6-api-{suffix}"
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g6-api-{suffix}")
    role = kernel_service.get_system_identity()["role_name"]
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        mount_response = requests.post(
            f"{base_url}/api/web/runtime/identity-kernel/mount",
            json={
                "session_id": session_id,
                "topics": [topic, "api-identity"],
                "risk_level": "high",
                "identity_package": _identity_package(role=role, suffix=f"api-{suffix}"),
            },
            timeout=60,
        )
        assert mount_response.status_code == 200, mount_response.text
        mounted = mount_response.json()
        query_response = requests.get(
            f"{base_url}/api/web/runtime/identity-kernel/anchors",
            params=[
                ("session_id", session_id),
                ("role", mounted["identity_kernel"]["role"]),
                ("risk_level", "high"),
                ("topics", topic),
            ],
            timeout=20,
        )
        evaluate_response = requests.post(
            f"{base_url}/api/web/runtime/identity-kernel/evaluate-change",
            json={
                "session_id": session_id,
                "proposed_changes": {
                    "role": "API Unapproved Executor",
                    "notes": "disable safety",
                },
                "human_confirmed": False,
            },
            timeout=20,
        )

    _assert_mount(mounted, topics=[topic, "api-identity"])
    first_anchor_id = mounted["mounted_anchors"][0]["memory_id"]
    assert real_ci_runtime.memory_service.get_record(first_anchor_id) is not None

    assert query_response.status_code == 200, query_response.text
    _assert_anchor_query(query_response.json(), expected_role=mounted["identity_kernel"]["role"], expected_topic=topic)

    assert evaluate_response.status_code == 200, evaluate_response.text
    blocked = evaluate_response.json()
    assert blocked["decision"] == "blocked"
    assert "role" in blocked["locked_change_fields"]
    assert "self_binding_constraint_violation" in blocked["violations"]
