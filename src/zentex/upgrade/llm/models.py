from __future__ import annotations

"""
Contracts for LLM upgrade planning.

This file defines the request and plan payloads used by the DSPy-facing
upgrade service so optimization jobs have explicit evidence, metrics, and
release targets before any runtime execution starts.
"""

from pydantic import BaseModel, ConfigDict, Field

from zentex.upgrade.versioning import UpgradeChangeScope


class LLMUpgradeRequest(BaseModel):
    """Structured input for planning an LLM optimization candidate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    program_id: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    target_metric: str = Field(min_length=1)
    dataset_refs: list[str] = Field(default_factory=list)
    optimizer_name: str = Field(default="mipro_v2", min_length=1)
    change_scope: UpgradeChangeScope = UpgradeChangeScope.MINOR
    objective_summary: str = Field(min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    # DSPy primitives (Function 59 gap)
    dspy_signature: Optional[str] = None
    dspy_module: Optional[str] = None
    dspy_metric: Optional[str] = None
    # Prompt optimization metadata
    upgrade_kind: Optional[str] = None
    prompt_file_path: Optional[str] = None
    prompt_builder_symbol: Optional[str] = None
    prompt_contract: dict[str, object] = Field(default_factory=dict)
    immutable_intent: Optional[str] = None
    forbidden_prompt_changes: list[str] = Field(default_factory=list)
    allowed_prompt_change_scope: list[str] = Field(default_factory=list)


class LLMUpgradeExecutionPlan(BaseModel):
    """Execution plan for a DSPy optimization run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(default="dspy", min_length=1)
    optimizer_name: str = Field(min_length=1)
    target_metric: str = Field(min_length=1)
    dataset_refs: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)
    # DSPy runtime options
    dspy_signature: Optional[str] = None
    dspy_metric: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)


class LLMUpgradeCandidate(BaseModel):
    """Candidate release contract returned by the LLM upgrade service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    program_id: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    candidate_version: str = Field(min_length=1)
    objective_summary: str = Field(min_length=1)
    execution_plan: LLMUpgradeExecutionPlan
    release_gate: list[str] = Field(default_factory=list)
    # Metadata for registry (Function 59 gap)
    dspy_signature: Optional[str] = None
    dspy_module: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
