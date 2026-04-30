from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from zentex.web_console.services.audit import build_audit_graph, build_audit_items


@dataclass(frozen=True)
class _AuditEntry:
    entry_id: str
    trace_id: str
    session_id: str
    turn_id: str
    entry_type: str
    timestamp: datetime
    source: str
    payload: dict[str, Any]


def test_external_connector_audit_events_build_workflow_graph_with_execution_evidence() -> None:
    trace_id = "task-mongodb-mongodb_create-audit-real"
    connector_id = "mongodb_crud_connector"
    capability = "mongodb_create"
    items = build_audit_items(
        [
            _AuditEntry(
                entry_id="connector-audit-1",
                trace_id=trace_id,
                session_id="external-connectors",
                turn_id="invocation-1",
                entry_type="connector_audit_event",
                timestamp=datetime.now(timezone.utc),
                source="external_connectors.service",
                payload={
                    "connector_id": connector_id,
                    "capability": capability,
                    "target_app": "mongodb",
                    "status": "success",
                    "profile_level": "verifiable",
                    "risk_level": "mutates_remote",
                    "verification_mode": "read_after_write",
                    "evidence_validation_status": "present",
                    "output_summary": {"post_query_count": 1},
                    "evidence_refs": [{"type": "mongodb_collection", "database": "zentex", "collection": "orders"}],
                },
            )
        ]
    )

    assert len(items) == 1
    assert items[0].summary == (
        "mongodb_create via mongodb_crud_connector status=success evidence=present"
    )
    assert items[0].context_info["connector_id"] == connector_id
    assert items[0].context_info["capability"] == capability
    assert items[0].context_info["evidence_validation_status"] == "present"

    graph = build_audit_graph(mode="external_connectors", audit_items=items, model_provider_traces=[])
    assert graph.mode == "external_connectors"
    assert graph.title == "基于外部连接器开始的审计与溯源"
    assert graph.summary["audit_event_count"] == 1
    assert graph.summary["module_families"]["external_connectors"]["event_count"] == 1

    execution_nodes = [node for lane in graph.lanes if lane.lane_id == "execution" for node in lane.nodes]
    assert len(execution_nodes) == 1
    execution = execution_nodes[0]
    assert execution.title == "mongodb_crud_connector / mongodb_create"
    assert execution.status == "active"
    assert execution.metrics["trace_id"] == trace_id
    assert execution.metrics["connector_id"] == connector_id
    assert execution.metrics["capability"] == capability
    assert execution.metrics["profile_level"] == "verifiable"
    assert execution.metrics["risk_level"] == "mutates_remote"
    assert execution.metrics["verification_mode"] == "read_after_write"
    assert execution.metrics["evidence_validation_status"] == "present"
