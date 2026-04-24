from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from zentex.web_console.contracts.audit_event import AuditEventPayload


class LLMStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    probe_checked: bool = False
    provider_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key_env: Optional[str] = None
    health_status: Optional[str] = None
    reason: Optional[str] = None
    missing_env: list[str] = Field(default_factory=list)
    hint: Optional[str] = None
    provider_error_type: Optional[str] = None


class RuntimeOverviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime: dict[str, Any]
    session: dict[str, Any]
    working_memory: dict[str, Any]
    metacognition: dict[str, Any]
    living_self_model: dict[str, Any]
    temporal_agenda: dict[str, Any]
    recent_events: list[AuditEventPayload] = Field(default_factory=list)
    last_intervention_event: Optional[AuditEventPayload] = None
    active_weight_plugin_id: Optional[str] = None
    weight_fallback_occurred: bool = False
    weight_profile: dict[str, Any] = Field(default_factory=dict)


class AuditEventStreamMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = "audit_event"
    event: AuditEventPayload
    overview: RuntimeOverviewPayload


class CognitiveAgendaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)


class CognitiveConflictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_version: int = 0
    brain_scope: Optional[str] = None


class SimulationBundlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle: dict[str, Any] = Field(default_factory=dict)


class InteractionMindPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: dict[str, Any] = Field(default_factory=dict)


class ConsolidationCyclesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycles: list[dict[str, Any]] = Field(default_factory=list)
