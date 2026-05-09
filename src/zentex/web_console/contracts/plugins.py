from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.plugins.contracts import BasePluginSpec, ManagedPluginRecord


REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_ROOT = REPO_ROOT / "docs"
SRC_ROOT = REPO_ROOT / "src"


class CognitivePluginStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str
    feature_code: str
    supports_multiple_plugins: bool = False
    plugin_kind: str
    version: str
    lifecycle_status: str
    operational_status: str
    health_status: Optional[str]
    purpose: str
    description: str
    used_in: list[str]
    is_default: bool = False
    is_official_release: bool = True
    can_force_enable: bool = False
    can_force_disable: bool = False
    can_delete: bool = False
    usage_count: int = 0
    failure_count: int = 0
    rollback_conditions: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_instantiated: bool = False


class ForceEnablePluginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin: CognitivePluginStatusItem
    auto_disabled_plugin_ids: list[str] = Field(default_factory=list)
    requires_override_warning: bool = False
    message: str




class ManagedForceEnableResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin_id: str
    auto_disabled_plugin_ids: list[str] = Field(default_factory=list)


class ManagedPluginTestSandbox(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    records: dict[str, ManagedPluginRecord]
    audit_events: list[dict[str, Any]] = Field(default_factory=list)

    def resolve_plugin_for_test(self, plugin_id: str) -> ManagedPluginRecord:
        try:
            return self.records[plugin_id]
        except KeyError as exc:
            raise KeyError(f"Unknown managed plugin: {plugin_id}") from exc


class PluginFeatureGroupItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_code: str
    display_name: str
    plugin_kind: str
    feature_guide_path: Optional[str] = None
    family_guide_path: Optional[str] = None
    supports_multiple_plugins: bool
    binding_status: str
    active_plugin_ids: list[str] = Field(default_factory=list)
    plugins: list[CognitivePluginStatusItem] = Field(default_factory=list)


class PluginVersionHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str
    version: str
    upgrade_status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    previous_version: Optional[str] = None


class PluginRelationshipItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin: CognitivePluginStatusItem
    role: str = "primary"
    priority: int = 1
    fallback_id: Optional[str] = None
    relationship_created_at: Optional[datetime] = None
    relationship_updated_at: Optional[datetime] = None


class CognitivePluginDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin: CognitivePluginStatusItem
    active_version_tool_id: Optional[str] = None
    related_versions: list[CognitivePluginStatusItem] = Field(default_factory=list)
    functional_plugins: list[PluginRelationshipItem] = Field(default_factory=list)
    history: list[PluginVersionHistoryItem] = Field(default_factory=list)


class FunctionalPluginDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin: CognitivePluginStatusItem
    cognitive_plugins: list[PluginRelationshipItem] = Field(default_factory=list)
    history: list[PluginVersionHistoryItem] = Field(default_factory=list)


class PluginActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_reason: str = Field(min_length=1)
    allow_overwrite_active: bool = False


class PluginRelationActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_reason: str = Field(min_length=1)
    role: str = "primary"
    priority: int = 1
    fallback_id: Optional[str] = None


class PluginTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class PluginTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str
    ok: bool
    details: dict[str, Any] = Field(default_factory=dict)


FEATURE_GUIDE_PATHS: dict[str, str] = {
    "weights:subjective_preferences": str(DOCS_ROOT / "operability/plugin_features/weights_subjective_preferences.md"),
    "identity:package_loader": str(DOCS_ROOT / "operability/plugin_features/identity_package_loader.md"),
}


PLUGIN_FAMILY_GUIDE_PATHS: dict[str, str] = {
    "cognitive_tool": str(SRC_ROOT / "plugins/cognitive/DEVELOPMENT_GUIDE.md"),
    "model_provider": str(SRC_ROOT / "plugins/model_providers/DEVELOPMENT_GUIDE.md"),
    "execution_domain": str(SRC_ROOT / "plugins/execution/DEVELOPMENT_GUIDE.md"),
    "simulation_domain": str(SRC_ROOT / "plugins/simulation/DEVELOPMENT_GUIDE.md"),
    "subjective_weight": str(SRC_ROOT / "plugins/weights/DEVELOPMENT_GUIDE.md"),
    "identity_package": str(DOCS_ROOT / "operability/plugin_features/identity_package_loader.md"),
}


# Resolve deferred ForwardRefs for Pydantic v2
CognitivePluginStatusItem.model_rebuild()
