from __future__ import annotations

from pathlib import Path
import importlib
import sys

import pytest


fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from zentex.common.plugin_registry import PluginNotBoundError  # noqa: E402
from zentex.web_console import api  # noqa: E402
from zentex.web_console import dev_server  # noqa: E402


def _fresh_client() -> TestClient:
    module = importlib.reload(dev_server)
    return TestClient(module.app)


def test_cognitive_plugins_expose_runtime_and_contract_metadata() -> None:
    client = _fresh_client()

    response = client.get("/api/web/plugins/cognitive")

    assert response.status_code == 200
    payload = response.json()
    risk_comparator = next(item for item in payload if item["tool_id"] == "risk-comparator")
    revoked = next(item for item in payload if item["tool_id"] == "decision-summarizer")
    idea_scout = next(item for item in payload if item["tool_id"] == "idea-scout")
    preview = next(item for item in payload if item["tool_id"] == "risk-lab-preview")

    assert risk_comparator["version"] == "1.0.0"
    assert risk_comparator["purpose"]
    assert risk_comparator["used_in"]
    assert risk_comparator["required_context"]
    assert risk_comparator["is_default"] is True
    assert risk_comparator["can_delete"] is False
    assert risk_comparator["created_at"] is not None
    assert risk_comparator["updated_at"] is not None
    assert risk_comparator["started_at"] is not None
    assert risk_comparator["last_used_at"] is not None

    assert revoked["status"] == "revoked"
    assert revoked["stopped_at"] is not None
    assert revoked["can_force_enable"] is True
    assert idea_scout["can_delete"] is True
    assert preview["can_force_enable"] is False


def test_plugins_endpoint_groups_by_feature_family() -> None:
    client = _fresh_client()

    response = client.get("/api/web/plugins")

    assert response.status_code == 200
    payload = response.json()
    risk_group = next(item for item in payload if item["feature_code"] == "risk_assessment")
    model_group = next(item for item in payload if item["feature_code"] == "core.model_provider")
    execution_group = next(item for item in payload if item["feature_code"] == "execution.system")
    weight_group = next(
        item for item in payload if item["feature_code"] == "weights:subjective_preferences"
    )
    identity_group = next(
        item for item in payload if item["feature_code"] == "identity:package_loader"
    )

    assert risk_group["supports_multiple_plugins"] is False
    assert risk_group["binding_status"] == "bound_active"
    assert risk_group["display_name"] == "风险评估"
    assert "risk-comparator" in risk_group["active_plugin_ids"]
    assert all("internal_revision_id" not in plugin for plugin in risk_group["plugins"])
    assert any(plugin["tool_id"] == "risk-lab-preview" for plugin in risk_group["plugins"])
    assert model_group["plugin_kind"] == "model_provider"
    assert model_group["binding_status"] == "bound_active"
    assert model_group["active_plugin_ids"] == ["model-provider-openai-compat"]
    assert execution_group["plugin_kind"] == "execution_domain"
    assert "execution-system-local" in execution_group["active_plugin_ids"]
    assert weight_group["plugin_kind"] == "subjective_weight"
    assert "default_conservative_weight" in weight_group["active_plugin_ids"]
    assert identity_group["binding_status"] == "unbound"
    assert identity_group["plugins"] == []

    evidence_group = next(item for item in payload if item["feature_code"] == "evidence_ranking")
    evidence_ranker = next(
        plugin for plugin in evidence_group["plugins"] if plugin["tool_id"] == "evidence-ranker"
    )
    assert evidence_ranker["can_force_disable"] is False
    assert evidence_group["binding_status"] == "bound_inactive"


def test_force_enable_endpoint_promotes_plugin_to_active() -> None:
    client = _fresh_client()

    response = client.post(
        "/api/web/plugins/decision-summarizer/force-enable",
        json={"audit_reason": "operator override for inspection"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin"]["tool_id"] == "decision-summarizer"
    assert payload["plugin"]["status"] == "active"
    assert payload["plugin"]["can_force_enable"] is False
    assert payload["auto_disabled_plugin_ids"] == []
    assert payload["message"] == "force_enabled"


def test_force_enable_endpoint_rejects_non_official_plugin() -> None:
    client = _fresh_client()

    response = client.post(
        "/api/web/plugins/risk-lab-preview/force-enable",
        json={"audit_reason": "attempted to force-enable preview build"},
    )

    assert response.status_code == 403


def test_force_disable_endpoint_restores_previous_official_plugin_for_single_behavior() -> None:
    client = _fresh_client()

    enable_response = client.post(
        "/api/web/plugins/idea-scout/force-enable",
        json={"audit_reason": "operator validation of candidate behavior"},
    )
    assert enable_response.status_code == 200
    assert enable_response.json()["plugin"]["tool_id"] == "idea-scout"
    assert enable_response.json()["plugin"]["status"] == "active"
    assert enable_response.json()["auto_disabled_plugin_ids"] == ["risk-comparator"]
    assert enable_response.json()["message"] == "force_enabled_with_auto_disable"

    disable_response = client.post(
        "/api/web/plugins/idea-scout/force-disable",
        json={"audit_reason": "candidate regression detected"},
    )

    assert disable_response.status_code == 200
    payload = disable_response.json()
    assert payload["tool_id"] == "risk-comparator"
    assert payload["status"] == "active"

    list_response = client.get("/api/web/plugins/cognitive")
    tools = {item["tool_id"]: item for item in list_response.json()}
    assert tools["idea-scout"]["status"] == "degraded"
    assert tools["risk-comparator"]["status"] == "active"


def test_delete_endpoint_removes_non_default_inactive_plugin() -> None:
    client = _fresh_client()

    response = client.request(
        "DELETE",
        "/api/web/plugins/idea-scout",
        json={"audit_reason": "candidate removed after manual review"},
    )

    assert response.status_code == 200
    assert response.json()["deleted_plugin_id"] == "idea-scout"

    list_response = client.get("/api/web/plugins/cognitive")
    tool_ids = [item["tool_id"] for item in list_response.json()]
    assert "idea-scout" not in tool_ids


def test_delete_endpoint_rejects_default_plugin_removal() -> None:
    client = _fresh_client()

    response = client.request(
        "DELETE",
        "/api/web/plugins/risk-comparator",
        json={"audit_reason": "attempted removal of default plugin"},
    )

    assert response.status_code == 403


def test_managed_plugin_force_enable_and_delete_use_generic_routes() -> None:
    client = _fresh_client()

    enable_response = client.post(
        "/api/web/plugins/execution-browser-cloud/force-enable",
        json={"audit_reason": "promote browser executor for cloud validation"},
    )

    assert enable_response.status_code == 200
    payload = enable_response.json()
    assert payload["plugin"]["tool_id"] == "execution-browser-cloud"
    assert payload["plugin"]["status"] == "active"

    delete_response = client.request(
        "DELETE",
        "/api/web/plugins/cost_guard_weight",
        json={"audit_reason": "retire sandbox-only weight profile"},
    )

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_plugin_id"] == "cost_guard_weight"


def test_managed_default_plugin_delete_is_blocked() -> None:
    client = _fresh_client()

    response = client.request(
        "DELETE",
        "/api/web/plugins/default_conservative_weight",
        json={"audit_reason": "attempted removal of default weight plugin"},
    )

    assert response.status_code == 403


def test_managed_runtime_resolution_requires_active_binding_and_test_sandbox_isolated() -> None:
    module = importlib.reload(dev_server)
    records = module.app.state.managed_plugin_records

    with pytest.raises(PluginNotBoundError, match="No active bound plugin"):
        api.resolve_managed_bound_plugins(
            "execution.browser",
            records,
            plugin_id="execution-browser-cloud",
        )

    sandbox = api.create_managed_plugin_test_sandbox(records)
    preview_record = sandbox.resolve_plugin_for_test("execution-browser-cloud")

    assert preview_record.plugin.plugin_id == "execution-browser-cloud"
    assert preview_record.plugin.status.value == "sandbox_verified"
    assert sandbox.records["execution-browser-cloud"] is not records["execution-browser-cloud"]
