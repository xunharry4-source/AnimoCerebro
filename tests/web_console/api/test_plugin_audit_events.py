from __future__ import annotations

from pathlib import Path
import importlib
import sys
from unittest import mock

import pytest


fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from zentex.web_console import dev_server  # noqa: E402


def _fresh_client() -> TestClient:
    module = importlib.reload(dev_server)
    return TestClient(module.app)


def test_managed_plugin_state_changes_append_audit_events() -> None:
    module = importlib.reload(dev_server)
    runtime = module.app.state.runtime

    # Hard requirement: every plugin state mutation must emit an auditable append(...)
    runtime.transcript_store.append = mock.Mock(wraps=runtime.transcript_store.append)

    client = TestClient(module.app)
    response = client.post(
        "/api/web/plugins/execution-browser-cloud/force-enable",
        json={"audit_reason": "promote browser executor for cloud validation"},
    )
    assert response.status_code == 200

    assert runtime.transcript_store.append.called
    last_event = runtime.transcript_store.append.call_args_list[-1].args[0]
    assert last_event["plugin_id"] == "execution-browser-cloud"
    assert last_event["action"] == "force_enabled"
    assert last_event["audit_reason"] == "promote browser executor for cloud validation"


def test_managed_plugin_delete_appends_audit_event() -> None:
    module = importlib.reload(dev_server)
    runtime = module.app.state.runtime
    runtime.transcript_store.append = mock.Mock(wraps=runtime.transcript_store.append)

    client = TestClient(module.app)
    response = client.request(
        "DELETE",
        "/api/web/plugins/cost_guard_weight",
        json={"audit_reason": "retire sandbox-only weight profile"},
    )
    assert response.status_code == 200

    assert runtime.transcript_store.append.called
    last_event = runtime.transcript_store.append.call_args_list[-1].args[0]
    assert last_event["plugin_id"] == "cost_guard_weight"
    assert last_event["action"] == "deleted"
    assert last_event["audit_reason"] == "retire sandbox-only weight profile"

