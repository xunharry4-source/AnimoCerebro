from __future__ import annotations

"""System identity API models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SystemIdentityConfig(BaseModel):
    """The single user-configured system role used by Q3 and later 9Q steps."""

    role_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="System role for Q3 'Who am I' / 用于 Q3“我是谁”的系统角色",
    )
    mission: str = Field(
        "",
        max_length=2000,
        description="Optional mission statement for the system role / 可选角色使命",
    )
    core_values: list[str] = Field(
        default_factory=list,
        description="Optional role boundaries and core values / 可选角色边界和核心价值",
    )

    @field_validator("role_name", "mission", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("core_values", mode="before")
    @classmethod
    def normalize_core_values(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role_name": "Full-stack Engineer",
                "mission": "Implement and verify changes with real tests.",
                "core_values": ["no fake tests", "do not hide backend errors"],
            }
        }
    )


class SystemIdentityResponse(BaseModel):
    """Response for reading or mutating the single system identity."""

    role_name: str = ""
    identity_role: str = ""
    mission: str = ""
    core_values: list[str] = Field(default_factory=list)
    user_configured: bool = False
    source: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    identity_kernel_snapshot: dict[str, Any] = Field(default_factory=dict)
