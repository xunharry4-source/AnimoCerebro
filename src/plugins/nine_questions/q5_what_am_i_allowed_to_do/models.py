from __future__ import annotations

from enum import Enum
from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExecutionTier(str, Enum):
    READ_ONLY = "read_only"
    CONSTRAINED_EXECUTE = "constrained_execute"
    FULL_EXECUTE = "full_execute"


class InteractionScope(str, Enum):
    DISABLED = "disabled"
    WHITELIST_ONLY = "whitelist_only"
    SAME_ORG_ONLY = "same_org_only"
    OPEN = "open"


class PermissionBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_tier: ExecutionTier
    interaction_scope: InteractionScope
    requires_human_confirmation: bool
    requires_cloud_audit: bool


class ComplianceChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_delegation_targets: List[str] = Field(default_factory=list)
    explicitly_forbidden_actions: List[str] = Field(default_factory=list)
    compliance_risks: List[str] = Field(default_factory=list)


class Q5InferenceResult(BaseModel):
    """
    Combined output specification for Zentex cognitive kernel phase 5.
    """
    model_config = ConfigDict(extra="forbid")

    permission_boundary: PermissionBoundary
    compliance_checklist: ComplianceChecklist


class AuthorizationBoundary(BaseModel):
    """
    Strict live-LLM output contract for Q5 cannot-do boundary.
    """
    model_config = ConfigDict(extra="forbid")

    current_authorization_scope: str = Field(
        min_length=1,
        description="当前禁止边界总体描述；概括本次交互中不能越过的最高权限域。",
    )
    communication_policy: str = Field(min_length=1)
    organizational_boundary: str = Field(min_length=1)
    allowed_operations: List[str] = Field(default_factory=list, description="未命中禁止边界的对照白名单。")
    forbidden_operations: List[str] = Field(default_factory=list, description="Q5 主输出：禁止、未授权、需升级或缺证据动作。")

    @field_validator("current_authorization_scope", "communication_policy", "organizational_boundary", mode="before")
    @classmethod
    def normalize_required_text(cls, value):
        return str(value or "").strip()

    @field_validator("allowed_operations", "forbidden_operations", mode="before")
    @classmethod
    def normalize_string_list(cls, value):
        if not isinstance(value, list):
            return value
        return [str(item or "").strip() for item in value if str(item or "").strip()]


class AuthorizationBoundaryEnvelope(BaseModel):
    """
    Root object required by the Q5 LLM system prompt.
    """
    model_config = ConfigDict(extra="forbid")

    AuthorizationBoundary: AuthorizationBoundary
