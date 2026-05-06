from __future__ import annotations
from typing import List, Optional, Any, Dict, Union
from pydantic import BaseModel, ConfigDict, Field
from zentex.cli.models import ToolUsageProfile

# Re-exporting from core contracts to maintain backward compatibility 
# while moving the source of truth to the core module.
from zentex.mcp.contracts import (
    McpServerToolItem,
    McpServerStatusItem,
    McpTaskSummary,
    McpServerDetailItem
)

class McpInlineCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_id: Optional[str] = None
    credential_type: str = Field(default="api_key", min_length=1)
    secret_payload: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class McpServerRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    server_id: str = Field(min_length=1)
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    protocol_version: str = "2024-11-05"
    tags: List[str] = Field(default_factory=list)
    owner: Optional[str] = None
    transport_type: str = Field(pattern="^(stdio|sse|http|streamable_http)$")
    command: str = Field(min_length=1)
    args: List[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    scope: List[str] = Field(default_factory=lambda: ["read"])
    auth_config: dict[str, object] = Field(default_factory=dict)
    auth_credential: Optional[McpInlineCredentialRequest] = None
    auth_mode: str = Field(default="none", pattern="^(none|bearer|api_key|oauth_pkce)$")
    tool_bindings: List[dict[str, object]] = Field(default_factory=list)
    help_doc_url: Optional[str] = None
    project_doc_url: Optional[str] = None
    documentation_learning_required: bool = True

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
