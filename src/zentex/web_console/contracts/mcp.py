from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

# Re-exporting from core contracts to maintain backward compatibility 
# while moving the source of truth to the core module.
from zentex.mcp.contracts import (
    McpServerToolItem,
    McpServerStatusItem,
    McpTaskSummary,
    McpServerDetailItem
)

class McpServerRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    server_id: str = Field(min_length=1)
    transport_type: str = Field(pattern="^(stdio|sse)$")
    command: str = Field(min_length=1)
    args: List[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

class McpToolTestCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)

class McpToolTestCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_id: str
    tool_name: str
    trace_id: str
    payload: dict[str, object] = Field(default_factory=dict)
