from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from zentex.reflection.models import ReflectionType


def test_reflection_learning_memory_and_audit_acceptance(client: TestClient) -> None:
    app = client.app
    suffix = uuid4().hex[:10]

    reflection = app.state.reflection_service.record_nine_question_reflection(
        subject=f"acceptance-reflection-{suffix}",
        reflection_type=ReflectionType.STRATEGY_REFLECTION,
        context={"question_id": "q2", "summary": f"reflection-summary-{suffix}"},
        trace_id=f"reflection-trace-{suffix}",
    )
    reflections_response = client.get(f"/api/web/reflections?q_id=q2&limit=100")
    assert reflections_response.status_code == 200
    reflections_payload = reflections_response.json()
    assert any(item["reflection_id"] == reflection.reflection_id for item in reflections_payload["items"])

    updated = app.state.reflection_service.update_reflection(
        reflection.reflection_id,
        {"context": {"question_id": "q2", "summary": f"updated-reflection-{suffix}"}},
    )
    assert updated.context["summary"] == f"updated-reflection-{suffix}"
    assert app.state.reflection_service.delete_reflection(reflection.reflection_id) is True
    deleted_reflections = client.get("/api/web/reflections?q_id=q2&limit=100")
    assert deleted_reflections.status_code == 200
    assert all(
        item["reflection_id"] != reflection.reflection_id
        for item in deleted_reflections.json()["items"]
    )

    app.state.learning_service.record_nine_question_learning(
        question_id="q3",
        learning_kind="acceptance",
        detail={"summary": f"learning-summary-{suffix}", "question_driver_refs": ["q3"]},
        trace_id=f"learning-trace-{suffix}",
    )
    learning_response = client.get("/api/web/learning/history?limit=100")
    assert learning_response.status_code == 200
    learning_rows = learning_response.json()["rows"]
    assert any(
        item["summary"] == f"learning-summary-{suffix}"
        and "q3" in item["question_driver_refs"]
        and item["direction"] == "nine_question_integration"
        for item in learning_rows
    )

    memory = app.state.memory_service.remember(
        title=f"acceptance-memory-{suffix}",
        summary=f"memory-summary-{suffix}",
        content=f"memory-content-{suffix}",
        layer="semantic",
        source="tests.ci_acceptance",
        trace_id=f"memory-trace-{suffix}",
        target_id=f"target-{suffix}",
        tags=["acceptance", suffix],
    )
    records_response = client.get(f"/api/web/memory/records?trace_id=memory-trace-{suffix}&limit=50")
    assert records_response.status_code == 200
    records_payload = records_response.json()
    assert any(item["memory_id"] == memory.memory_id for item in records_payload["items"])

    update_response = client.post(
        f"/api/web/memory/{memory.memory_id}/management",
        json={
            "status": "active",
            "visibility": "public",
            "trust_level": "verified",
            "reason": "acceptance update",
            "operator": "ci_acceptance",
        },
    )
    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["status"] == "active"
    assert update_payload["visibility"] == "public"
    assert update_payload["trust_level"] == "verified"
    memory_detail = client.get(f"/api/web/memory/{memory.memory_id}")
    assert memory_detail.status_code == 200
    assert memory_detail.json()["memory_id"] == memory.memory_id
    assert memory_detail.json()["trust_level"] == "verified"

    audit = app.state.audit_service.record_nine_question_audit(
        question_id="q4",
        module_id="acceptance_audit",
        summary=f"audit-summary-{suffix}",
        payload={"suffix": suffix},
        trace_id=f"audit-trace-{suffix}",
        session_id=f"session-{suffix}",
        turn_id=f"turn-{suffix}",
        source="tests.ci_acceptance",
    )
    audit_response = client.get("/api/web/audits?page=1&page_size=100")
    assert audit_response.status_code == 200
    audit_rows = audit_response.json()["items"]
    assert any(
        item["trace_id"] == f"audit-trace-{suffix}"
        and item["summary"] == f"audit-summary-{suffix}"
        for item in audit_rows
    )
    flow_response = client.get("/api/web/audit/flow-health")
    assert flow_response.status_code == 200
    assert audit["audit_id"] in str(flow_response.json())
