from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field


class InterventionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    phase_name: str = "manual"
    manual_context_patch: Dict[str, Any] = Field(default_factory=dict)

