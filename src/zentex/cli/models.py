from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
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
    project_doc_url: Optional[str] = None
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

class CliToolRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_name: str
    description: str
    mapped_domain: Literal["cognitive", "execution"]
    cli_id: str
    feature_code: str
    execution_domain: Optional[str] = None
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    status: Literal["active", "degraded", "revoked", "stopped"] = "active"
    help_doc_url: Optional[str] = None
    project_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None

class ToolUsageProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    usage_summary: str
    supported_commands: List[str] = Field(default_factory=list)
    supported_tools: List[str] = Field(default_factory=list)
    argument_schema: Dict[str, Any] = Field(default_factory=dict)
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    side_effects: List[str] = Field(default_factory=list)
    auth_requirements: List[str] = Field(default_factory=list)
    risk_notes: List[str] = Field(default_factory=list)
    task_routing_hints: List[str] = Field(default_factory=list)
    source_type: Literal["cli", "mcp"]
    source_refs: List[str] = Field(default_factory=list)
    degraded: bool = False
    learning_status: Literal["learned", "degraded", "simulated_learned"] = "learned"

class CliInvocationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    status: Literal["success", "failed", "timeout", "transport_error"]
    trace_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command_line: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    duration_ms: int = 0
    failure_category: Optional[str] = None
    preflight_blocked: bool = False

class CliCreditScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_score: float = Field(ge=0.0, le=100.0)
    success_rate: float = Field(ge=0.0, le=1.0)
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    average_response_time_ms: Optional[float] = None
    error_rate: float = Field(ge=0.0, le=1.0)
    usage_frequency: str = "low"  # low, medium, high
    credit_level: str  # excellent, good, fair, poor
    last_updated: str

class CliTaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    title: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    priority: str = "medium"
    remarks: Optional[str] = None

class CliExecutionHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str
    tool_name: str
    status: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command_line: List[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
    executed_at: str
    duration_ms: Optional[int] = None
    failure_category: Optional[str] = None
    preflight_blocked: bool = False
