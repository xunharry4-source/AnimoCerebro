from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

class McpToolBindingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    tool_name: str = Field(min_length=1)
    domain: Literal["cognitive", "execution"]
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    execution_domain: str = "mcp"

    @model_validator(mode="after")
    def validate_domain_boundary(self) -> "McpToolBindingConfig":
        if self.domain == "cognitive":
            if self.mutates_state or self.read_only is not True or self.side_effect_free is not True:
                raise ValueError(
                    "Cognitive MCP tools must remain read_only=True, side_effect_free=True, mutates_state=False"
                )
        return self

class McpServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    server_id: str = Field(min_length=1)
    name: Optional[str] = None  # 友好的显示名称
    description: Optional[str] = None  # 服务器介绍/描述
    version: Optional[str] = None  # 版本号
    protocol_version: str = "2024-11-05"
    tags: List[str] = Field(default_factory=list)  # 标签列表
    owner: Optional[str] = None  # 所有者/负责人
    transport_type: Literal["stdio", "sse", "http", "streamable_http"]
    command: str = Field(min_length=1)
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    scope: List[str] = Field(default_factory=lambda: ["read"])
    auth_mode: Literal["none", "bearer", "api_key", "oauth_pkce"] = "none"
    tool_bindings: List[McpToolBindingConfig] = Field(default_factory=list)
    help_doc_url: Optional[str] = None
    project_doc_url: Optional[str] = None
    documentation_learning_required: bool = True

class McpToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    description: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    mutates_state: bool = False
    read_only_hint: bool = True

class McpToolRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    description: str
    mapped_domain: Literal["cognitive", "execution"]
    mcp_id: str
    feature_code: str
    execution_domain: Optional[str] = None
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    status: Literal["active", "degraded", "revoked"] = "active"

class McpServerRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_id: str
    name: Optional[str] = None  # 友好的显示名称
    description: Optional[str] = None  # 服务器介绍/描述
    version: Optional[str] = None  # 版本号
    tags: List[str] = Field(default_factory=list)  # 标签列表
    owner: Optional[str] = None  # 所有者/负责人
    transport_type: Literal["stdio", "sse", "http", "streamable_http"]
    status: Literal["online", "offline", "degraded"]
    tool_count: int = 0
    error_message: Optional[str] = None
    tools: List[McpToolRuntimeState] = Field(default_factory=list)
    protocol_version: str = "2024-11-05"
    scope: List[str] = Field(default_factory=lambda: ["read"])
    auth_mode: str = "none"
    help_doc_url: Optional[str] = None
    project_doc_url: Optional[str] = None

    @property
    def lifecycle_status(self) -> str:
        return self.status
