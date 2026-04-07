from __future__ import annotations

from enum import Enum
from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field


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
