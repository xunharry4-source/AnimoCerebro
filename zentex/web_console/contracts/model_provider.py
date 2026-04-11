from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.web_console.contracts.llm_trace import LLMTracePayload
from zentex.web_console.contracts.transcript import TranscriptEventPayload


class ModelProviderTraceItem(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    trace_id: str
    request_id: str
    decision_id: str
    phase_name: str
    session_id: str
    turn_id: str
    provider_plugin_id: str
    provider_name: str | None = None
    model: str | None = None
    source_module: str | None = None
    invocation_phase: str | None = None
    question_driver_refs: list[str] = Field(default_factory=list)
    invoked_at: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None
    prompt: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    request_driver: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    related_events: list[TranscriptEventPayload] = Field(default_factory=list)
    preprocessed_evidence: dict[str, Any] | None = None
    inference_result: dict[str, Any] | None = None
    q1_llm_upgrade: dict[str, Any] | None = None
    llm_trace_payload: LLMTracePayload | None = None


ModelProviderTraceItem.model_rebuild()
