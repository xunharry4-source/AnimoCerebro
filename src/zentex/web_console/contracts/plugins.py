from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.core.plugin_base import BasePluginSpec
from pathlib import Path

# Resolve repo root dynamically to avoid hardcoded paths
REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent
DOCS_ROOT = REPO_ROOT / "docs"
SRC_ROOT = REPO_ROOT / "src"


class CognitivePluginStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: str
    feature_code: str
    supports_multiple_plugins: bool = False
    plugin_kind: str
    version: str
    status: str
    health_status: Optional[str]
    purpose: str
    description: str
    used_in: List[str]
    is_default: bool = False
    is_official_release: bool = True
    can_force_enable: bool = False
    can_force_disable: bool = False
    can_delete: bool = False
    usage_count: int
    failure_count: int
    rollback_conditions: List[str]
    trigger_conditions: List[str]
    required_context: List[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class ForceEnablePluginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin: CognitivePluginStatusItem
    auto_disabled_plugin_ids: List[str] = Field(default_factory=list)
    requires_override_warning: bool = False
    message: str


class ManagedPluginRecord(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin: BasePluginSpec
    internal_revision_id: int = Field(ge=1)
    source_kind: Literal["builtin", "user", "test_stub"] = "builtin"
    description: str = Field(min_length=1)
    feature_code: str
    supports_multiple_plugins: bool = False
    is_default: bool = False
    is_official_release: bool = True
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None


class ManagedForceEnableResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin_id: str
    auto_disabled_plugin_ids: List[str] = Field(default_factory=list)


class ManagedPluginTestSandbox(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    records: Dict[str, ManagedPluginRecord]
    audit_events: List[Dict[str, Any]] = Field(default_factory=list)

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
    active_plugin_ids: List[str] = Field(default_factory=list)
    plugins: List[CognitivePluginStatusItem] = Field(default_factory=list)


class PluginFeatureCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_code: str
    display_name: str
    plugin_kind: str
    feature_guide_path: Optional[str] = None
    family_guide_path: Optional[str] = None
    supports_multiple_plugins: bool = False


class PluginActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_reason: str = Field(min_length=1)
    allow_overwrite_active: bool = False


class PluginTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class PluginTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str
    ok: bool
    details: Dict[str, Any] = Field(default_factory=dict)


FEATURE_GUIDE_PATHS: Dict[str, str] = {
    "risk_assessment": str(DOCS_ROOT / "operability/plugin_features/risk_assessment.md"),
    "evidence_ranking": str(DOCS_ROOT / "operability/plugin_features/evidence_ranking.md"),
    "decision_summary": str(DOCS_ROOT / "operability/plugin_features/decision_summary.md"),
    "cognitive_conflict_detection": str(DOCS_ROOT / "operability/plugin_features/cognitive_conflict_detection.md"),
    "memory_consolidation": str(DOCS_ROOT / "operability/plugin_features/memory_consolidation.md"),
    "model_provider:gemini": str(DOCS_ROOT / "operability/plugin_features/model_provider_gemini.md"),
    "model_provider:openai_compat": str(DOCS_ROOT / "operability/plugin_features/model_provider_openai_compat.md"),
    "sensory_ingest:webhook": str(DOCS_ROOT / "operability/plugin_features/sensory_ingest_webhook.md"),
    "sensory_sanitize:basic_prompt_injection_sanitizer": str(DOCS_ROOT / "operability/plugin_features/sensory_sanitize_basic_prompt_injection_sanitizer.md"),
    "sensory_interpret:generic_environment": str(DOCS_ROOT / "operability/plugin_features/sensory_interpret_generic_environment.md"),
    "execution:system": str(DOCS_ROOT / "operability/plugin_features/execution_system.md"),
    "execution:browser": str(DOCS_ROOT / "operability/plugin_features/execution_browser.md"),
    "simulation:general,system,cloud,browser,code,market": str(DOCS_ROOT / "operability/plugin_features/simulation_general.md"),
    "simulation:market": str(DOCS_ROOT / "operability/plugin_features/simulation_market.md"),
    "weights:subjective_preferences": str(DOCS_ROOT / "operability/plugin_features/weights_subjective_preferences.md"),
    "identity:package_loader": str(DOCS_ROOT / "operability/plugin_features/identity_package_loader.md"),
}


PLUGIN_FAMILY_GUIDE_PATHS: Dict[str, str] = {
    "cognitive_tool": str(SRC_ROOT / "plugins/cognitive/DEVELOPMENT_GUIDE.md"),
    "model_provider": str(SRC_ROOT / "plugins/model_providers/DEVELOPMENT_GUIDE.md"),
    "signal_ingest": str(SRC_ROOT / "plugins/sensory/DEVELOPMENT_GUIDE.md"),
    "signal_sanitize": str(SRC_ROOT / "plugins/sensory/DEVELOPMENT_GUIDE.md"),
    "signal_interpret": str(SRC_ROOT / "plugins/sensory/DEVELOPMENT_GUIDE.md"),
    "execution_domain": str(SRC_ROOT / "plugins/execution/DEVELOPMENT_GUIDE.md"),
    "simulation_domain": str(SRC_ROOT / "plugins/simulation/DEVELOPMENT_GUIDE.md"),
    "subjective_weight": str(SRC_ROOT / "plugins/weights/DEVELOPMENT_GUIDE.md"),
    "identity_package": str(DOCS_ROOT / "operability/plugin_features/identity_package_loader.md"),
}

