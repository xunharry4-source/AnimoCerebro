from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CliAdapterOverview:
    adapter_id: str
    status: str
    healthy: bool
    total_tools: int
    cognitive_tools: int
    execution_tools: int
    degraded_tools: int
    stopped_tools: int
    tools: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "status": self.status,
            "healthy": self.healthy,
            "total_tools": self.total_tools,
            "cognitive_tools": self.cognitive_tools,
            "execution_tools": self.execution_tools,
            "degraded_tools": self.degraded_tools,
            "stopped_tools": self.stopped_tools,
            "tools": self.tools,
        }


def build_cli_adapter_overview(service: Any) -> CliAdapterOverview:
    if service is None:
        raise ValueError("CLI service is not available")

    tools = list(service.list_tools())
    tool_rows = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        for item in tools
    ]
    cognitive_tools = sum(1 for item in tool_rows if item.get("mapped_domain") == "cognitive")
    execution_tools = sum(1 for item in tool_rows if item.get("mapped_domain") == "execution")
    degraded_tools = sum(1 for item in tool_rows if item.get("status") == "degraded")
    stopped_tools = sum(1 for item in tool_rows if item.get("status") == "stopped")
    healthy = degraded_tools == 0 and all(item.get("status") == "active" for item in tool_rows)
    status = "healthy" if healthy else "degraded"
    if not tool_rows:
        status = "healthy"
        healthy = True

    return CliAdapterOverview(
        adapter_id="cli-adapter-dev",
        status=status,
        healthy=healthy,
        total_tools=len(tool_rows),
        cognitive_tools=cognitive_tools,
        execution_tools=execution_tools,
        degraded_tools=degraded_tools,
        stopped_tools=stopped_tools,
        tools=tool_rows,
    )

