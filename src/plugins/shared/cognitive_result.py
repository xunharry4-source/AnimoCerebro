from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CognitiveToolResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_id: str
    summary: str
    proposals: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    uncertainties: list[dict[str, Any]] = Field(default_factory=list)
    context_updates: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
