"""
Workspace Models / 工作区数据模型

Pydantic models for workspace configuration and management.
工作区配置和管理的 Pydantic 模型。
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class WorkspaceConfig(BaseModel):
    """
    Workspace configuration model.
    
    Represents a single workspace that the system can analyze and operate on.
    工作区配置模型，代表系统可分析和操作的单个工作区。
    """

    id: Optional[int] = Field(None, description="Database ID")
    name: str = Field(..., min_length=1, max_length=255, description="Workspace display name / 工作区显示名")
    path: str = Field(..., min_length=1, description="Absolute path to workspace root / 工作区根目录的绝对路径")
    description: Optional[str] = Field(None, max_length=1000, description="Optional description / 可选描述")
    is_default: bool = Field(False, description="Is this the default workspace? / 是否为默认工作区")
    role: Optional[str] = Field(None, max_length=255, description="User-defined role for this workspace / 工作区的用户定义角色")
    role_description: Optional[str] = Field(None, max_length=2000, description="Detailed description of the role / 角色的详细描述")
    forbidden_actions: Optional[str] = Field(None, max_length=3000, description="Restrictions - what should NOT be done in this workspace / 限制项 - 在此工作区中不允许做什么")
    task_goals: Optional[str] = Field(None, max_length=5000, description="JSON array of task goals for this workspace / 此工作区的任务目标列表（JSON数组格式）")
    created_at: Optional[datetime] = Field(default_factory=_now, description="Creation timestamp / 创建时间戳")
    updated_at: Optional[datetime] = Field(default_factory=_now, description="Last update timestamp / 最后更新时间戳")

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, v: str) -> str:
        """Normalize path to absolute path."""
        from pathlib import Path
        return str(Path(v).resolve())

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "Main Project",
                "path": "/home/user/projects/main",
                "description": "Main backend project",
                "is_default": True,
                "created_at": "2026-04-11T10:00:00+00:00",
            }
        }


class WorkspaceListResponse(BaseModel):
    """Response model for workspace listing."""

    workspaces: list[WorkspaceConfig] = Field(..., description="List of workspaces")
    total: int = Field(..., description="Total workspace count")


class WorkspaceActionResponse(BaseModel):
    """Response model for workspace CRUD operations."""

    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Status message")
    workspace: Optional[WorkspaceConfig] = Field(None, description="Affected workspace if applicable")
