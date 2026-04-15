from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class McpServerToolItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    description: str
    mapped_domain: str
    mcp_id: str
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

class McpTaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    task_id: Optional[str] = None
    action_type: str
    status: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    verification_status: str
    error: Optional[str] = None

class McpServerDetailItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server_id: str
    transport_type: str
    status: str
    tool_count: int
    credit_score: int
    total_tasks_run: int
    success_rate: float
    uptime_seconds: int
    tools: List[McpServerToolItem]
    error_message: Optional[str] = None
