from __future__ import annotations

from typing import Optional, List, Dict, Any
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CliToolItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_name: str
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
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None


class CliToolRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tool_name: str = Field(min_length=1)
    command_executable: str = Field(min_length=1)
    command_args: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    read_only_flag: bool = True
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    execution_domain: str = "cli"
    env: dict[str, str] = Field(default_factory=dict)


class CliToolTestCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: list[str] = Field(default_factory=list)
    stdin_input: Optional[str] = None
    working_directory: Optional[str] = None
    timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)


class CliToolTestCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    status: str
    trace_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command_line: list[str] = Field(default_factory=list)
    working_directory: Optional[str] = None


class CliTaskSummary(BaseModel):
    """CLI 任务摘要信息"""
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
    """CLI 执行历史记录"""
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


class CliCreditScore(BaseModel):
    """CLI 工具信用分"""
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


class CliToolDetailResponse(BaseModel):
    """CLI 工具详细信息响应"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    # 基本信息
    command_name: str
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
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    
    # 信用分
    credit_score: CliCreditScore
    
    # 任务统计
    task_statistics: Dict[str, int] = Field(default_factory=dict)
