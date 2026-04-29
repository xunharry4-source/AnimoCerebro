from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LLMTokenUsagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMTracePayload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    request_id: Optional[str] = None
    decision_id: Optional[str] = None
    provider_name: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    prompt: Optional[str] = None
    source_module: Optional[str] = None
    invocation_phase: Optional[str] = None
    question_driver_refs: list[str] = Field(default_factory=list)
    context_data: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Optional[Any]] = None
    token_usage: LLMTokenUsagePayload = Field(default_factory=LLMTokenUsagePayload)
    elapsed_ms: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


LLMTokenUsagePayload.model_rebuild()
LLMTracePayload.model_rebuild()
