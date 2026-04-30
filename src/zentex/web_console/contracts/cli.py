from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

# Re-exporting from core models
from zentex.cli.models import (
    CliCreditScore,
    CliTaskSummary,
    CliExecutionHistory,
    CliInvocationResult,
    CliToolRuntimeState,
    ToolUsageProfile,
)

class CliToolRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    auth_required_for_health: bool = False
    health_probe_args: List[str] = Field(default_factory=list)
    help_probe_args: List[str] = Field(default_factory=lambda: ["--help"])
    version_probe_args: List[str] = Field(default_factory=lambda: ["--version"])
    documentation_learning_required: bool = True

class CliInvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    arguments: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None


class CliToolItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    command_name: str
    description: str
    mapped_domain: str
    cli_id: str
    feature_code: str
    execution_domain: Optional[str] = None
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    status: str = "active"
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None


class CliToolTestCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: List[str] = Field(default_factory=list)
    stdin_input: Optional[str] = None
    working_directory: Optional[str] = None
    timeout_seconds: int = 30


class CliToolTestCallResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tool_name: str
    status: str
    trace_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command_line: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    duration_ms: int = 0
    failure_category: Optional[str] = None
    preflight_blocked: bool = False


class CliToolDetailResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    command_name: str
    description: str
    mapped_domain: str
    cli_id: str
    feature_code: str
    execution_domain: Optional[str] = None
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    status: str = "active"
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    credit_score: Optional[CliCreditScore] = None
    task_statistics: Optional[Dict] = None
