from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

class PluginLayer(str, Enum):
    FUNCTIONAL = "functional"
    LOGICAL_COGNITIVE = "cognitive"

class PluginLifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    SANDBOX_VERIFIED = "sandbox_verified"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REVOKED = "revoked"

class BasePluginSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    plugin_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    feature_code: str = Field(min_length=1)
    lifecycle_status: PluginLifecycleStatus
    operational_status: str = "enabled"
    category: str = "functional"
    behavior_key: Optional[str] = None
    plugin_layer: PluginLayer = PluginLayer.FUNCTIONAL


class PluginFeatureCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_code: str
    display_name: str
    plugin_kind: str
    feature_guide_path: Optional[str] = None
    family_guide_path: Optional[str] = None
    supports_multiple_plugins: bool = False
