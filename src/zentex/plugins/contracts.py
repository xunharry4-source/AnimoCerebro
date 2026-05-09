from __future__ import annotations
"""Public plugin contracts for the migration away from zentex.core.plugin_base.

This file is the stable plugin-facing contract layer owned by zentex.plugins.
Legacy `zentex.core.plugin_base` imports bridge into this module during migration.
"""


from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class PluginLayer(str, Enum):
    FUNCTIONAL = "functional"
    LOGICAL_COGNITIVE = "cognitive"


class PluginLifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    SANDBOX_VERIFIED = "sandbox_verified"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REVOKED = "revoked"


class PluginHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class BasePluginSpec(BaseModel):
    """Migration-safe plugin contract compatible with legacy plugin specs."""

    model_config = ConfigDict(extra="allow", frozen=True, str_strip_whitespace=True, serialize_by_alias=True)

    plugin_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    feature_code: str = Field(default="", min_length=0)
    is_concurrency_safe: bool = False
    lifecycle_status: PluginLifecycleStatus = Field(
        default=PluginLifecycleStatus.CANDIDATE,
        validation_alias=AliasChoices("lifecycle_status", "status"),
        serialization_alias="status",
    )
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN
    health_probe_endpoint: Optional[str] = None
    rollback_conditions: list[str] = Field(default_factory=list)
    revocation_reasons: list[str] = Field(default_factory=list)
    operational_status: str = "enabled"
    category: str = "functional"  # 模块分类：functional(功能模块), cognitive(认知模块), sensory(感知模块) 等
    behavior_key: Optional[str] = None
    plugin_layer: PluginLayer = PluginLayer.FUNCTIONAL

    # 新增字段：插件分类（认知插件/功能插件）
    plugin_category: Optional[str] = Field(
        default=None,
        description="插件分类：cognitive(认知插件) 或 functional(功能插件)，用于区分插件的业务类型"
    )

    # 新增字段：插件地址（URL 或路径）
    plugin_url: Optional[str] = Field(
        default=None,
        description="插件地址：可以是 URL、文件路径或模块路径，用于定位插件源码或文档"
    )

    # 新增字段：插件说明
    description: Optional[str] = Field(
        default=None,
        description="插件说明：详细描述插件的功能、用途和使用场景"
    )
    is_instantiated: bool = False

    @classmethod
    def plugin_kind(cls) -> str:
        return "base_plugin"

    @property
    def status(self) -> PluginLifecycleStatus:
        return self.lifecycle_status

    def transition_to(self, target_status: PluginLifecycleStatus) -> "BasePluginSpec":
        return self.model_copy(update={"lifecycle_status": target_status})

    @model_validator(mode="after")
    def validate_lifecycle_contract(self) -> "BasePluginSpec":
        if self.lifecycle_status == PluginLifecycleStatus.ACTIVE and not self.rollback_conditions:
            raise ValueError("Active plugins must explicitly define rollback_conditions")
        if self.lifecycle_status in {PluginLifecycleStatus.DEGRADED, PluginLifecycleStatus.REVOKED} and not self.revocation_reasons:
            raise ValueError("Must provide reasons for degradation or revocation")
        return self


class FunctionalPluginSpec(BasePluginSpec):
    plugin_layer: PluginLayer = PluginLayer.FUNCTIONAL
    category: str = "functional"


class LogicalCognitivePluginSpec(BasePluginSpec):
    plugin_layer: PluginLayer = PluginLayer.LOGICAL_COGNITIVE
    category: str = "cognitive"


class SubjectiveWeightSpec(BasePluginSpec, ABC):
    category: str = "weight"

    @abstractmethod
    def calculate_weight(self, task_context: dict[str, Any]) -> float: ...


BasePluginSpec.model_rebuild()
FunctionalPluginSpec.model_rebuild()
LogicalCognitivePluginSpec.model_rebuild()
SubjectiveWeightSpec.model_rebuild()


class ManagedPluginRecord(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    plugin: Union[BasePluginSpec, Any]
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


ManagedPluginRecord.model_rebuild()

# Re-export from models for backward compatibility
from zentex.plugins.models import PluginFeatureCatalogItem as PluginFeatureCatalogItem
