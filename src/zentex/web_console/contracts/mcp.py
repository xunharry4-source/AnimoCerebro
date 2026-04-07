from __future__ import annotations
from typing import List, Optional


from pydantic import BaseModel, ConfigDict, Field


class McpServerToolItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    description: str
    mapped_domain: str
    plugin_id: str
    feature_code: str
    execution_domain: Optional[str] = None
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    status: str


class McpServerStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_id: str
    transport_type: str
    status: str
    tool_count: int = 0
    error_message: Optional[str] = None
    tools: List[McpServerToolItem] = Field(default_factory=list)


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
