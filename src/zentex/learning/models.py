from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolKnowledgeRecord(BaseModel):
    tool_name: str
    description: str
    usage_example: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    source_ref: str


class SandboxValidationResult(BaseModel):
    is_safe: bool
    behavior_fingerprint: str
    security_events: List[str] = Field(default_factory=list)
    performance_metrics: Dict[str, float] = Field(default_factory=dict)
