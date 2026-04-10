from __future__ import annotations
from typing import Dict, List, Literal, Optional
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class PluginLifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    SANDBOX_VERIFIED = "sandbox_verified"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REVOKED = "revoked"

class CliToolRegistrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    tool_name: str = Field(min_length=1)
    command_executable: str = Field(min_length=1)
    command_args: List[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    read_only_flag: bool = True
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    execution_domain: str = "cli"
    env: Dict[str, str] = Field(default_factory=dict)

class CliToolRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_name: str
    description: str
    mapped_domain: Literal["cognitive", "execution"]
    plugin_id: str
    feature_code: str
    execution_domain: Optional[str] = None
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    status: Literal["active", "degraded", "revoked"] = "active"
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None

class CliInvocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    status: Literal["success", "failed"]
    trace_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command_line: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
