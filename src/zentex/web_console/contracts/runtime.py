from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.web_console.contracts.transcript import TranscriptEventPayload


class LLMStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    probe_checked: bool = False
    provider_name: str | None = None
    api_base: str | None = None
    api_key_env: str | None = None
    health_status: str | None = None
    reason: str | None = None
    missing_env: list[str] = Field(default_factory=list)
    hint: str | None = None
    provider_error_type: str | None = None


class RuntimeOverviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime: dict[str, Any]
    session: dict[str, Any] | None
    working_memory: dict[str, Any]
    metacognition: dict[str, Any]
    living_self_model: dict[str, Any]
    temporal_agenda: dict[str, Any]
    recent_events: list[TranscriptEventPayload] = Field(default_factory=list)
    last_intervention_event: TranscriptEventPayload | None = None
    active_weight_plugin_id: str | None = None
    weight_fallback_occurred: bool = False
    weight_profile: dict[str, Any] = Field(default_factory=dict)


class TranscriptStreamMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = "transcript_event"
    event: TranscriptEventPayload
    overview: RuntimeOverviewPayload


class CognitiveAgendaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)


class CognitiveConflictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_version: int = 0
    brain_scope: str | None = None


class SimulationBundlePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle: dict[str, Any] = Field(default_factory=dict)


class InteractionMindPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: dict[str, Any] = Field(default_factory=dict)


class ConsolidationCyclesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycles: list[dict[str, Any]] = Field(default_factory=list)
