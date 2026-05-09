from __future__ import annotations

import os
import platform
import socket
from typing import Any

from pydantic import BaseModel, ConfigDict

from zentex.plugins.models import PluginLifecycleStatus


class HostTelemetryPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "sensory_telemetry"
    version: str = "1.0.0"
    feature_code: str = "sensory.telemetry"
    display_name: str = "Host Telemetry"
    description: str = "Collect read-only local host telemetry for Q1 environment evidence."
    behavior_key: str = "sensory_telemetry"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def capture_host_state(self, context: dict[str, Any]) -> dict[str, Any]:
        workspace_root = str(
            context.get("workspace_root")
            or context.get("cwd")
            or os.getcwd()
        )
        return {
            "cwd": workspace_root,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "memory_pressure": "unknown",
            "network_health": "unknown",
        }


def build_default_host_telemetry_plugin() -> HostTelemetryPlugin:
    return HostTelemetryPlugin()
