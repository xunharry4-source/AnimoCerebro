from __future__ import annotations

from fastapi.testclient import TestClient


def test_plugin_management_acceptance(client: TestClient) -> None:
    plugin_rows = client.get("/api/web/plugins")
    assert plugin_rows.status_code == 200
    all_plugins = plugin_rows.json()
    assert isinstance(all_plugins, list)

    functional_rows = client.get("/api/web/plugins/functional")
    assert functional_rows.status_code == 200
    functional_plugins = functional_rows.json()
    assert isinstance(functional_plugins, list)

    candidate_plugin_id = "sensory_environment"
    assert any(item.get("tool_id") == candidate_plugin_id for item in functional_plugins)

    disabled = client.post(f"/api/web/plugins/{candidate_plugin_id}/force-disable")
    assert disabled.status_code == 200
    assert disabled.json()["tool_id"] == candidate_plugin_id
    assert disabled.json()["operational_status"] == "stopped"
    enabled = client.post(
        f"/api/web/plugins/{candidate_plugin_id}/force-enable",
        json={"audit_reason": "acceptance"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["plugin"]["tool_id"] == candidate_plugin_id
    assert enabled.json()["plugin"]["operational_status"] == "enabled"
