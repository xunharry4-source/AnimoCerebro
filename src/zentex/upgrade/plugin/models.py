from __future__ import annotations

"""
Contracts for plugin upgrade planning.

This file defines the request and plan payloads used to evolve an existing
plugin into a new candidate version with isolated writes, startup checks, and
validation commands. The source plugin is treated as immutable; all automated
changes must happen on a copied candidate plugin directory.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zentex.upgrade.versioning import UpgradeChangeScope


class PluginEvolutionAction(str, Enum):
    """Supported plugin evolution actions."""

    UPGRADE = "upgrade"
    CREATE = "create"


class PluginUpgradeRequest(BaseModel):
    """Structured input for planning an OpenHands-driven plugin upgrade."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plugin_id: str = Field(min_length=1)
    plugin_path: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    allowed_write_paths: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    startup_commands: list[str] = Field(default_factory=list)
    change_scope: UpgradeChangeScope = UpgradeChangeScope.MINOR
    requested_capabilities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_write_scope(self) -> "PluginUpgradeRequest":
        if not self.allowed_write_paths:
            raise ValueError(
                "allowed_write_paths must not be empty for plugin evolution"
            )
        return self


class PluginUpgradeExecutionPlan(BaseModel):
    """Execution contract for a plugin evolution run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(default="openhands", min_length=1)
    workspace_strategy: str = Field(default="isolated_worktree_clone", min_length=1)
    source_plugin_path: str = Field(min_length=1)
    candidate_plugin_path: str = Field(min_length=1)
    version_update_strategy: str = Field(default="copy_then_bump_version", min_length=1)
    allowed_write_paths: list[str] = Field(default_factory=list)
    startup_commands: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    requested_capabilities: list[str] = Field(default_factory=list)


class PluginUpgradeCandidate(BaseModel):
    """Candidate release contract returned by the plugin upgrade service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str = Field(min_length=1)
    source_plugin_path: str = Field(min_length=1)
    candidate_plugin_path: str = Field(min_length=1)
    baseline_version: str = Field(min_length=1)
    candidate_version: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    execution_plan: PluginUpgradeExecutionPlan
    release_gate: list[str] = Field(default_factory=list)


class PluginCreationRequest(BaseModel):
    """Structured input for planning a new plugin candidate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plugin_id: str = Field(min_length=1)
    target_root_path: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    initial_version: str = Field(default="0.1.0", min_length=1)
    validation_commands: list[str] = Field(default_factory=list)
    startup_commands: list[str] = Field(default_factory=list)
    requested_capabilities: list[str] = Field(default_factory=list)


class PluginCreationExecutionPlan(BaseModel):
    """Execution contract for creating a new plugin candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(default="openhands", min_length=1)
    workspace_strategy: str = Field(default="isolated_candidate_scaffold", min_length=1)
    candidate_plugin_path: str = Field(min_length=1)
    version_update_strategy: str = Field(default="create_candidate_at_version", min_length=1)
    allowed_write_paths: list[str] = Field(default_factory=list)
    startup_commands: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    requested_capabilities: list[str] = Field(default_factory=list)


class PluginCreationCandidate(BaseModel):
    """Candidate release contract returned for new plugin creation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str = Field(min_length=1)
    candidate_plugin_path: str = Field(min_length=1)
    initial_version: str = Field(min_length=1)
    candidate_version: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    execution_plan: PluginCreationExecutionPlan
    release_gate: list[str] = Field(default_factory=list)
