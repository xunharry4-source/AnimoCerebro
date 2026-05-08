from __future__ import annotations

import logging
from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q2_internal_instructor_not_installed") from exc


class InternalCognitiveTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    capability_summary: str = Field(min_length=1)
    description: str = Field(min_length=1)
    function_description: str = Field(min_length=1)
    task_routing_hints: str = Field(default="")
    side_effects: str = Field(default="无外部副作用")


class InternalFunctionalPlugin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    capability_summary: str = Field(min_length=1)
    description: str = Field(min_length=1)
    function_description: str = Field(min_length=1)
    task_routing_hints: str = Field(default="")
    side_effects: str = Field(default="无外部副作用")


class LongTermMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    freshness: str = Field(min_length=1)


class ReusableStrategyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    applicable_scenario: str = Field(min_length=1)


class InternalAssetInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_cognitive_tools: List[InternalCognitiveTool] = Field(default_factory=list)
    internal_functional_plugins: List[InternalFunctionalPlugin] = Field(default_factory=list)
    long_term_memories: List[LongTermMemory] = Field(default_factory=list)
    reusable_strategy_patches: List[ReusableStrategyPatch] = Field(default_factory=list)


class InternalAssetInventorySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    InternalAssetInventory: InternalAssetInventory


def validate_internal_asset_inventory_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = InternalAssetInventorySet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q2_internal_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_internal_asset_inventory_set_with_instructor_contract(
    provider: Any,
    *,
    prompt: str,
    context: dict[str, Any],
    caller_context: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_instructor_runtime()
    raw_output = provider.generate_json(
        prompt=prompt,
        context=context,
        caller_context=caller_context,
        metadata={
            **(metadata or {}),
            "instructor_contract": "InternalAssetInventorySet",
            "response_model": "InternalAssetInventorySet",
        },
    )
    return validate_internal_asset_inventory_set(raw_output)
