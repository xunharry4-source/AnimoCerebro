from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


class ConnectorType(str, Enum):
    API_APP = "api_app"
    DESKTOP_APP = "desktop_app"
    BROWSER_APP = "browser_app"
    FILE_APP = "file_app"
    SERVICE_BRIDGE = "service_bridge"
    SDK_APP = "sdk_app"


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    REVOKED = "revoked"


class ConnectorRiskLevel(str, Enum):
    READ_ONLY = "read_only"
    WRITES_FILE = "writes_file"
    MUTATES_REMOTE = "mutates_remote"
    EXECUTES_LOCAL = "executes_local"


class ConnectorHealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class ConnectorProfileLevel(str, Enum):
    MINIMAL = "minimal"
    DESCRIBED = "described"
    VERIFIABLE = "verifiable"
    GOVERNED = "governed"


class ConnectorVerificationMode(str, Enum):
    NONE = "none"
    EVIDENCE = "evidence"
    READ_AFTER_WRITE = "read_after_write"
    EXTERNAL_QUERY = "external_query"
    MANUAL = "manual"


class ConnectorCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1)
    description: str = Field(default="")
    read_only: bool = True
    side_effect_type: str = "none"
    risk_level: ConnectorRiskLevel = ConnectorRiskLevel.READ_ONLY
    profile_level: ConnectorProfileLevel = ConnectorProfileLevel.MINIMAL
    verification_mode: ConnectorVerificationMode = ConnectorVerificationMode.NONE
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    evidence_required: bool = True


class ConnectorRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    connector_id: str = Field(min_length=1)
    connector_type: ConnectorType
    target_app: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str = ""
    connection_config: dict[str, Any] = Field(default_factory=dict)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    permission_scope: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[ConnectorCapability] = Field(default_factory=list)
    profile_level: ConnectorProfileLevel = ConnectorProfileLevel.MINIMAL
    runtime: str = ""
    version: str = ""
    manifest_path: str | None = None
    manifest_hash: str | None = None

    @field_validator("connector_id")
    @classmethod
    def validate_connector_id(cls, value: str) -> str:
        if not all(ch.isalnum() or ch in {"_", "-", "."} for ch in value):
            raise ValueError("connector_id may only contain letters, numbers, '-', '_' and '.'")
        return value


class ConnectorUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str | None = None
    description: str | None = None
    connection_config: dict[str, Any] | None = None
    auth_config: dict[str, Any] | None = None
    permission_scope: dict[str, Any] | None = None
    capabilities: list[ConnectorCapability] | None = None
    status: ConnectorStatus | None = None
    profile_level: ConnectorProfileLevel | None = None


class ExternalConnectorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    connector_type: ConnectorType
    target_app: str
    display_name: str
    description: str = ""
    connection_config: dict[str, Any] = Field(default_factory=dict)
    auth_config: dict[str, Any] = Field(default_factory=dict)
    permission_scope: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[ConnectorCapability] = Field(default_factory=list)
    profile_level: ConnectorProfileLevel = ConnectorProfileLevel.MINIMAL
    runtime: str = ""
    version: str = ""
    manifest_path: str | None = None
    manifest_hash: str | None = None
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ConnectorHealthReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    target_app: str
    health_status: ConnectorHealthStatus
    checked_at: datetime = Field(default_factory=utc_now)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None
    error_stage: str | None = None
    operator_message: str | None = None
    trace_id: str


class ConnectorTestCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    dry_run: bool = False


class ConnectorInvocationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invocation_id: str = Field(default_factory=lambda: f"connector-invocation-{uuid4().hex}")
    connector_id: str
    target_app: str
    capability: str
    trace_id: str
    status: Literal["success", "failed"]
    input_summary: dict[str, Any]
    output_summary: dict[str, Any] = Field(default_factory=dict)
    before_evidence: dict[str, Any] = Field(default_factory=dict)
    after_evidence: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    profile_level: ConnectorProfileLevel = ConnectorProfileLevel.MINIMAL
    risk_level: ConnectorRiskLevel = ConnectorRiskLevel.READ_ONLY
    verification_mode: ConnectorVerificationMode = ConnectorVerificationMode.NONE
    evidence_validation_status: Literal["not_required", "present", "failed"] = "not_required"
    error_code: str | None = None
    error_stage: str | None = None
    operator_message: str | None = None
    recovery_hint: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ConnectorError(Exception):
    def __init__(
        self,
        *,
        error_code: str,
        error_stage: str,
        operator_message: str,
        recovery_hint: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(operator_message)
        self.error_code = error_code
        self.error_stage = error_stage
        self.operator_message = operator_message
        self.recovery_hint = recovery_hint
        self.status_code = status_code
