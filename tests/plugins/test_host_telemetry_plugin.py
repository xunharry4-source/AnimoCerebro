from __future__ import annotations

from plugins.sensory.host_telemetry_plugin import build_default_host_telemetry_plugin
from zentex.runtime.nine_questions.startup_snapshot import build_runtime_workspace_snapshot


def test_host_telemetry_plugin_captures_real_host_state() -> None:
    plugin = build_default_host_telemetry_plugin()

    payload = plugin.capture_host_state({})

    assert payload["hostname"]
    assert payload["platform"]
    assert payload["python_version"]
    assert payload["memory_pressure"] in {"normal", "medium", "high", "critical", "unknown"}
    assert payload["network_health"] in {"healthy", "degraded", "offline"}


def test_startup_snapshot_uses_host_telemetry_plugin() -> None:
    plugin = build_default_host_telemetry_plugin()

    snapshot = build_runtime_workspace_snapshot(
        workspace_root=".",
        cognitive_registry=None,
        execution_registry=None,
        task_service=None,
        environment_summary="test snapshot",
        host_telemetry_plugin=plugin,
    )

    host_state = snapshot["physical_host_state"]
    assert isinstance(host_state, dict)
    assert host_state["hostname"]
    assert host_state["memory_pressure"] in {"normal", "medium", "high", "critical", "unknown"}
    assert host_state["network_health"] in {"healthy", "degraded", "offline"}
