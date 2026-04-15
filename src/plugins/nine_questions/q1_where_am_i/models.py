from __future__ import annotations
from typing import List


from pydantic import BaseModel, ConfigDict, Field


class WorkspaceDomainInference(BaseModel):
    """
    Strict output contract for "Q1: 我在哪" inference.

    Hard requirements:
    - Missing any required field is a hard failure (fail-closed).
    - secondary_domains must allow mixed scenarios (code + billing, etc).
    """

    model_config = ConfigDict(extra="forbid")

    primary_domain: str = Field(min_length=1)
    secondary_domains: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = Field(min_length=1)
    uncertainties: List[str] = Field(default_factory=list, min_length=1)
    suggested_first_step: str = Field(min_length=1)
    host_runtime_type: str | None = Field(default=None)
    host_runtime_reason: str | None = Field(default=None)

