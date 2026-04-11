from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMTokenUsagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMTracePayload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    request_id: str | None = None
    decision_id: str | None = None
    provider_name: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    prompt: str | None = None
    source_module: str | None = None
    invocation_phase: str | None = None
    question_driver_refs: list[str] = Field(default_factory=list)
    context_data: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Any] | None = None
    token_usage: LLMTokenUsagePayload = Field(default_factory=LLMTokenUsagePayload)
    elapsed_ms: int | None = None
    error_type: str | None = None
    error_message: str | None = None
