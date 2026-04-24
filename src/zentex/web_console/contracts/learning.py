from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class LearningDirectionPlanItem(BaseModel):
    id: str
    architecture_ref: str
    title_zh: str
    title_en: str
    body_zh: str
    body_en: str


class LearningRedlinesSummary(BaseModel):
    zh: str
    en: str


class LearningPlanResponse(BaseModel):
    directions: List[LearningDirectionPlanItem]
    redlines: LearningRedlinesSummary


class LearningHistoryRow(BaseModel):
    entry_id: str
    timestamp: str
    trace_id: str
    session_id: str = ""
    replay_event_id: str = ""
    kind: str
    direction: str
    verified: bool
    summary: str
    architecture_ref: str = ""
    question_driver_refs: List[str] = Field(default_factory=list)


class LearningHistoryResponse(BaseModel):
    rows: List[LearningHistoryRow]


class LearningRunCycleRequest(BaseModel):
    direction: str = Field(
        ...,
        description="LearningDirection value, e.g. g24_curiosity",
    )
    dry_run: bool = Field(default=False, description="If true, only records intent; no LLM.")
    load_factor: float = Field(default=0.0, ge=0.0, le=1.0, description="System load 0-1; high values pause learning.")
    extra_context: Optional[Dict[str, Any]] = Field(default=None, description="Optional metadata (e.g. doc_url for G16)")


class LearningRunCycleResponse(BaseModel):
    trace_id: str
    turn_id: str
    status: str
    detail: Dict[str, Any] = Field(default_factory=dict)
