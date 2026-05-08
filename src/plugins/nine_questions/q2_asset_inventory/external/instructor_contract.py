from __future__ import annotations

import logging
from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


def _require_instructor_runtime() -> None:
    try:
        import instructor  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("q2_external_instructor_not_installed") from exc


class ExternalToolAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    capability_summary: str = Field(min_length=1)
    description: str = Field(min_length=1)
    function_description: str = Field(min_length=1)
    task_routing_hints: str = Field(min_length=1)
    side_effects: str = Field(min_length=1)
    verification_status: Literal["真实已验证", "未验证"]


class ExternalAgentAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    expertise: str = Field(min_length=1)
    verification_status: Literal["真实已验证", "未验证"]
    credibility_level: Literal["高", "低"]


class ExternalAssetInventory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available_external_tools: List[ExternalToolAsset] = Field(default_factory=list)
    external_agents: List[ExternalAgentAsset] = Field(default_factory=list)
    unverified_external_warnings: List[str] = Field(default_factory=list)


class ExternalAssetInventorySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ExternalAssetInventory: ExternalAssetInventory


def validate_external_asset_inventory_set(raw_output: dict[str, Any]) -> dict[str, Any]:
    _require_instructor_runtime()
    try:
        validated = ExternalAssetInventorySet.model_validate(raw_output)
    except ValidationError as exc:
        raise RuntimeError(f"q2_external_instructor_validation_failed:{exc}") from exc
    return validated.model_dump(mode="json")


def generate_external_asset_inventory_set_with_instructor_contract(
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
            "instructor_contract": "ExternalAssetInventorySet",
            "response_model": "ExternalAssetInventorySet",
        },
    )
    return validate_external_asset_inventory_set(raw_output)
