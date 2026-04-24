from __future__ import annotations

"""
Upgrade models for Q1 LLM evolution.

This file keeps the Q1-specific LLM upgrade payloads separate from the main Q1
inference schema so the plugin can expose upgrade planning metadata without
mixing it into the runtime inference contract.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class Q1LLMUpgradeProfile(BaseModel):
    """Static upgrade profile describing how Q1 should be optimized."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    program_id: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    target_metric: str = Field(min_length=1)
    objective_summary: str = Field(min_length=1)
    dataset_refs: List[str] = Field(default_factory=list)
    validation_commands: List[str] = Field(default_factory=list)


class Q1LLMUpgradePlanPayload(BaseModel):
    """Structured upgrade planning output exposed by the Q1 plugin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    planning_status: str = Field(min_length=1)
    profile: Q1LLMUpgradeProfile
    candidate_version: Optional[str] = None
    release_gate: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
