from __future__ import annotations

"""
Top-level decision models for controlled upgrade routing.

This file defines the generic request and decision contracts used by the
upgrade facade so callers can ask one method to decide whether an LLM should
be upgraded or whether a plugin should be upgraded, created, or skipped.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zentex.upgrade.llm.models import LLMUpgradeCandidate, LLMUpgradeRequest
from zentex.upgrade.plugin.models import (
    PluginCreationCandidate,
    PluginCreationRequest,
    PluginEvolutionAction,
    PluginUpgradeCandidate,
    PluginUpgradeRequest,
)
from zentex.upgrade.base_models import (
    UpgradeTargetKind,
    SelfUpgradeProposal,
    CandidatePatch,
    VerificationBundle,
    PromotionDecision,
)
from typing import List, Dict, Any, Optional, Union
from uuid import uuid4
from datetime import datetime, UTC


class UpgradeDecisionAction(str, Enum):
    """Generic decision outcomes for top-level upgrade routing."""

    SKIP = "skip"
    UPGRADE = "upgrade"
    CREATE = "create"


class UpgradeMemoryContext(BaseModel):
    """Summarized memory recall context used before planning an upgrade."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)
    recalled_memory_ids: list[str] = Field(default_factory=list)
    success_patterns: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    suspect_patterns: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class LLMUpgradeIntentRequest(BaseModel):
    """Top-level request for deciding whether an LLM optimization is needed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1)
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    change_signals: list[str] = Field(default_factory=list)
    upgrade_required: Optional[bool] = None
    upgrade_request: LLMUpgradeRequest


class LLMUpgradeDecision(BaseModel):
    """Decision returned by the generic LLM upgrade method."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: UpgradeDecisionAction
    rationale: str = Field(min_length=1)
    candidate: Optional[LLMUpgradeCandidate] = None
    memory_context: Optional[UpgradeMemoryContext] = None


class PluginEvolutionIntentRequest(BaseModel):
    """Top-level request for deciding plugin upgrade vs. new plugin creation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1)
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    source_event_id: Optional[str] = None
    parent_record_id: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    change_signals: list[str] = Field(default_factory=list)
    requested_action: Optional[PluginEvolutionAction] = None
    upgrade_request: Optional[PluginUpgradeRequest] = None
    creation_request: Optional[PluginCreationRequest] = None

    @model_validator(mode="after")
    def validate_payload_presence(self) -> "PluginEvolutionIntentRequest":
        if self.requested_action is PluginEvolutionAction.UPGRADE and self.upgrade_request is None:
            raise ValueError("upgrade_request is required when requested_action is 'upgrade'")
        if self.requested_action is PluginEvolutionAction.CREATE and self.creation_request is None:
            raise ValueError("creation_request is required when requested_action is 'create'")
        if self.requested_action is None and self.upgrade_request is None and self.creation_request is None:
            raise ValueError(
                "at least one of upgrade_request or creation_request must be provided"
            )
        return self


class PluginEvolutionDecision(BaseModel):
    """Decision returned by the generic plugin evolution method."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: UpgradeDecisionAction
    rationale: str = Field(min_length=1)
    upgrade_candidate: Optional[PluginUpgradeCandidate] = None
    creation_candidate: Optional[PluginCreationCandidate] = None
    memory_context: Optional[UpgradeMemoryContext] = None
