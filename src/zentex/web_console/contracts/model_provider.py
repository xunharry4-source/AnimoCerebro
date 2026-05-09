from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from zentex.web_console.contracts.llm_trace import LLMTracePayload
from zentex.web_console.contracts.audit_event import AuditEventPayload


class ModelProviderTraceItem(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    trace_id: str
    request_id: str
    decision_id: str
    phase_name: str
    session_id: str
    turn_id: str
    provider_plugin_id: str
    provider_name: Optional[str] = None
    model: Optional[str] = None
    source_module: Optional[str] = None
    invocation_phase: Optional[str] = None
    question_driver_refs: list[str] = Field(default_factory=list)
    invoked_at: Optional[str] = None
    completed_at: Optional[str] = None
    failed_at: Optional[str] = None
    prompt: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)
    request_driver: dict[str, Any] = Field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    related_events: list[AuditEventPayload] = Field(default_factory=list)
    preprocessed_evidence: Optional[dict[str, Any]] = None
    inference_result: Optional[dict[str, Any]] = None
    q1_llm_upgrade: Optional[dict[str, Any]] = None
    llm_trace_payload: Optional[LLMTracePayload] = None


ModelProviderTraceItem.model_rebuild()
