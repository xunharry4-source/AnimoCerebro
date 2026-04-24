from __future__ import annotations
from typing import List


from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResourceStatus(str, Enum):
    sufficient = "sufficient"
    degraded = "degraded"
    critically_lacking = "critically_lacking"


class UnifiedAssetInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_cognitive_tools: List[str] = Field(default_factory=list)
    available_execution_tools: List[str] = Field(default_factory=list)
    connected_agents: List[dict] = Field(default_factory=list)
    activated_strategy_patches: List[str] = Field(default_factory=list)
    accessible_workspace_zones: List[str] = Field(default_factory=list)


class ResourceEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_status: ResourceStatus
    missing_critical_assets: List[str] = Field(default_factory=list)
    bottleneck_node: str = Field(min_length=1)
    reasoning_summary: str | None = None

    @field_validator("bottleneck_node", mode="before")
    @classmethod
    def normalize_bottleneck_node(cls, value):
        if value is None:
            return "none"
        text = str(value).strip()
        return text or "none"


class Q3WhatDoIHaveInference(BaseModel):
    """
    Strict LLM output contract for Q3.
    """

    model_config = ConfigDict(extra="forbid")

    unified_asset_inventory: UnifiedAssetInventory
    resource_evaluation: ResourceEvaluation
