from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def _functional_status(base_url: str, plugin_id: str) -> dict:
    response = requests.get(f"{base_url}/api/web/plugins/functional/{plugin_id}", timeout=10)
    assert response.status_code == 200, response.text
    return response.json()["plugin"]


def test_plugin_management_acceptance(acceptance_app: FastAPI) -> None:
    with live_http_server(acceptance_app) as base_url:
        plugin_rows = requests.get(f"{base_url}/api/web/plugins", timeout=10)
        assert plugin_rows.status_code == 200
        all_plugins = plugin_rows.json()
        assert isinstance(all_plugins, list)

        cognitive_rows = requests.get(f"{base_url}/api/web/plugins/cognitive", timeout=10)
        assert cognitive_rows.status_code == 200
        cognitive_plugins = cognitive_rows.json()
        assert isinstance(cognitive_plugins, list)
        assert cognitive_plugins, "real plugin bootstrap should expose cognitive plugins"
        assert all(
            item.get("plugin_kind") in {"cognitive", "cognitive_tool"}
            for item in cognitive_plugins
        ), "cognitive endpoint must only expose cognitive plugins"

        functional_rows = requests.get(f"{base_url}/api/web/plugins/functional", timeout=10)
        assert functional_rows.status_code == 200
        functional_plugins = functional_rows.json()
        assert isinstance(functional_plugins, list)
        assert all(item.get("plugin_kind") == "functional" for item in functional_plugins), (
            "functional endpoint must only expose plugins from service category=functional"
        )

        candidate_plugin_id = "document_router"
        assert any(item.get("tool_id") == candidate_plugin_id for item in functional_plugins)

        enabled_first = requests.post(
            f"{base_url}/api/web/plugins/{candidate_plugin_id}/force-enable",
            json={"audit_reason": "acceptance"},
            timeout=10,
        )
        assert enabled_first.status_code == 200
        assert enabled_first.json()["plugin"]["tool_id"] == candidate_plugin_id
        assert enabled_first.json()["plugin"]["operational_status"] == "enabled"
        assert _functional_status(base_url, candidate_plugin_id)["operational_status"] == "enabled"

        disabled = requests.post(f"{base_url}/api/web/plugins/{candidate_plugin_id}/force-disable", timeout=10)
        assert disabled.status_code == 200
        assert disabled.json()["tool_id"] == candidate_plugin_id
        assert disabled.json()["operational_status"] == "stopped"
        assert _functional_status(base_url, candidate_plugin_id)["operational_status"] == "stopped"

        enabled = requests.post(
            f"{base_url}/api/web/plugins/{candidate_plugin_id}/force-enable",
            json={"audit_reason": "acceptance"},
            timeout=10,
        )
        assert enabled.status_code == 200
        assert enabled.json()["plugin"]["tool_id"] == candidate_plugin_id
        assert enabled.json()["plugin"]["operational_status"] == "enabled"
        assert _functional_status(base_url, candidate_plugin_id)["operational_status"] == "enabled"

        missing = requests.post(
            f"{base_url}/api/web/plugins/missing-plugin-for-acceptance/force-disable",
            timeout=10,
        )
        assert missing.status_code == 404
        assert "missing-plugin-for-acceptance" in str(missing.json()["detail"])
