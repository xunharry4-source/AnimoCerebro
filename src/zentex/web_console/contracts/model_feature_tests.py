from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ModelFeatureTestCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_id: str
    display_name: str
    description: str
    group: str = "default"
    supports_simulation: bool = False
    enabled: bool = True


class ModelFeatureInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_id: str
    prompt: str = Field(min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)
    caller_context: Dict[str, Any] = Field(default_factory=dict)


class ModelFeatureInvokeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    test_run_id: str
    result: Dict[str, Any] = Field(default_factory=dict)


class ModelFeatureStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_id: Optional[str] = None
    total_runs: int = 0
    ok_runs: int = 0
    failed_runs: int = 0
    avg_input_tokens: float = 0.0
    avg_output_tokens: float = 0.0
    avg_total_tokens: float = 0.0
    last_run_at: Optional[str] = None
    last_ok_at: Optional[str] = None
    last_failed_at: Optional[str] = None


class ModelFeatureHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    test_run_id: str
    feature_id: str
    started_at: str
    finished_at: str
    ok: bool
    summary: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ModelFeatureRunLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    test_run_id: str
    record: Dict[str, Any] | None

