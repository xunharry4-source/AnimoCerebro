from __future__ import annotations

"""
Unified plugin base contract for Zentex.

This module defines the lowest-level plugin specification shared by all future
plugin families, including model providers, sensory adapters, simulation
plugins, identity packages, and cognitive tools.

The contract is intentionally strict because pluginization in Zentex is not a
best-effort extension point. Every plugin must declare enough lifecycle,
health, rollback, and revocation metadata for the runtime to:

- isolate failure at the plugin boundary
- degrade safely without crashing the main brain loop
- roll back to the last audited healthy version
- preserve auditable revocation and rollback reasons

BasePluginSpec / 统一插件基类

EN:
BasePluginSpec is the abstract Pydantic v2 base model for all Zentex plugins.
It enforces lifecycle status, health-probe visibility, and rollback metadata.

ZH:
BasePluginSpec（统一插件基类）是 Zentex 所有插件的抽象 Pydantic v2 基类模
型。它强制约束插件生命周期状态、健康探针可见性，以及回退与撤销元数据。
"""

from abc import ABC, abstractmethod
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Set
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PluginLifecycleStatus(str, Enum):
    """Lifecycle state of a plugin instance or registered plugin version."""

    CANDIDATE = "candidate"
    SANDBOX_VERIFIED = "sandbox_verified"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REVOKED = "revoked"


class PluginHealthStatus(str, Enum):
    """Lightweight health state used when no explicit endpoint is available."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class PluginLayer(str, Enum):
    """Hard runtime layer for plugin call-graph isolation."""

    LOGICAL_COGNITIVE = "logical_cognitive"
    FUNCTIONAL = "functional"


class BasePluginSpec(BaseModel, ABC):
    """
    Abstract base contract for all plugin specifications in Zentex.

    Required defenses:
    - [Failure Isolation & Degrade]
      A plugin must expose a health contract through either
      `health_probe_endpoint` or `health_status`.
    - [Rollback & State Recovery]
      A plugin must declare rollback and revocation metadata so the runtime can
      isolate and safely fall back to the last audited healthy version.

    Lifecycle discipline:
    - candidate -> sandbox_verified -> active is the normal promotion path
    - active may later degrade or be revoked
    - illegal jumps are blocked by `transition_to`
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        use_enum_values=False,
        str_strip_whitespace=True,
    )

    plugin_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    feature_code: str = Field(min_length=1)
    plugin_layer: PluginLayer
    is_concurrency_safe: bool
    status: PluginLifecycleStatus

    health_probe_endpoint: Optional[str] = Field(default=None, min_length=1)
    health_status: Optional[PluginHealthStatus] = None

    rollback_conditions: List[str]
    revocation_reasons: List[str]

    @classmethod
    @abstractmethod
    def plugin_kind(cls) -> str:
        """Return the stable plugin family identifier."""

    @classmethod
    def plugin_layer_kind(cls) -> PluginLayer:
        """
        Return the enforced runtime layer for this plugin family.

        The base default is functional so existing generic plugin specs stay
        fail-closed until explicitly promoted into the logical-cognitive layer.
        """

        return PluginLayer.FUNCTIONAL

    @model_validator(mode="before")
    @classmethod
    def populate_feature_code(cls, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        payload.setdefault("plugin_layer", cls.plugin_layer_kind())
        raw_feature_code = payload.get("feature_code")
        if isinstance(raw_feature_code, str) and raw_feature_code.strip():
            return payload

        plugin_id = str(payload.get("plugin_id") or "").strip()
        kind = ""
        try:
            kind = str(cls.plugin_kind() or "").strip()
        except Exception:
            kind = ""

        derived: Optional[str] = None
        if kind == "model_provider":
            derived = "core.model_provider"
        elif kind == "signal_ingest":
            derived = "sensory.ingest"
        elif kind == "signal_sanitize":
            derived = "sensory.sanitize"
        elif kind == "signal_interpret":
            derived = "sensory.interpret"
        elif kind == "execution_domain":
            execution_domain = str(payload.get("execution_domain") or "").strip()
            derived = f"execution.{execution_domain}" if execution_domain else "execution"
        elif kind == "simulation_domain":
            domains = payload.get("supported_domains")
            if isinstance(domains, list) and domains:
                if len(domains) == 1:
                    derived = f"simulation.{domains[0]}"
                else:
                    derived = "simulation.bundle"
            else:
                derived = "simulation.bundle"
        elif kind == "subjective_weight":
            derived = "weights:subjective_preferences"
        elif kind == "cognitive_tool":
            tool_type = str(payload.get("tool_type") or "").strip()
            behavior_key = str(payload.get("behavior_key") or "").strip()
            if tool_type == "nine_question" or "nine_question" in plugin_id or "nine-question" in plugin_id:
                match = re.search(r"q([1-9])", plugin_id)
                if match:
                    derived = f"nine_questions.q{match.group(1)}"
                else:
                    derived = "nine_questions"
            else:
                derived = behavior_key or plugin_id or "cognitive_tool"

        if derived is None:
            derived = f"{kind}:{plugin_id}" if kind and plugin_id else (kind or plugin_id or "unknown")

        payload["feature_code"] = derived
        return payload

    @model_validator(mode="after")
    def validate_runtime_safety_contract(self) -> "BasePluginSpec":
        if self.plugin_layer != self.plugin_layer_kind():
            raise ValueError(
                "Plugin layer does not match the declared plugin base contract: "
                f"{self.plugin_layer.value} != {self.plugin_layer_kind().value}"
            )

        has_health_endpoint = self.health_probe_endpoint is not None
        has_health_status = self.health_status is not None

        if not has_health_endpoint and not has_health_status:
            raise ValueError(
                "Plugin must declare health_probe_endpoint or health_status "
                "for failure isolation."
            )

        if self.status == PluginLifecycleStatus.ACTIVE and not self.rollback_conditions:
            raise ValueError("Active plugins must explicitly define rollback_conditions")

        if self.status in {
            PluginLifecycleStatus.DEGRADED,
            PluginLifecycleStatus.REVOKED,
        } and not self.revocation_reasons:
            raise ValueError("Must provide reasons for degradation or revocation")

        return self

    def transition_to(
        self,
        status: PluginLifecycleStatus,
        *,
        revocation_reasons: List[str] | None = None,
    ) -> Self:
        """
        Return a validated copy moved to the next lifecycle state.

        This method prevents illegal lifecycle jumps so plugin promotion and
        rollback management cannot silently skip required verification stages.
        """

        allowed_transitions: Dict[PluginLifecycleStatus, Set[PluginLifecycleStatus]] = {
            PluginLifecycleStatus.CANDIDATE: {
                PluginLifecycleStatus.SANDBOX_VERIFIED,
                PluginLifecycleStatus.REVOKED,
            },
            PluginLifecycleStatus.SANDBOX_VERIFIED: {
                PluginLifecycleStatus.ACTIVE,
                PluginLifecycleStatus.DEGRADED,
                PluginLifecycleStatus.REVOKED,
            },
            PluginLifecycleStatus.ACTIVE: {
                PluginLifecycleStatus.DEGRADED,
                PluginLifecycleStatus.REVOKED,
            },
            PluginLifecycleStatus.DEGRADED: {
                PluginLifecycleStatus.ACTIVE,
                PluginLifecycleStatus.REVOKED,
            },
            PluginLifecycleStatus.REVOKED: set(),
        }

        if status == self.status:
            return self

        if status not in allowed_transitions[self.status]:
            raise ValueError(
                f"Illegal plugin status transition: {self.status.value} -> {status.value}"
            )

        update_payload: Dict[str, object] = {"status": status}
        if revocation_reasons is not None:
            update_payload["revocation_reasons"] = revocation_reasons
        return self.model_copy(update=update_payload)


class LogicalCognitivePluginSpec(BasePluginSpec, ABC):
    """Top-layer reasoning plugins that may orchestrate lower functional plugins."""

    @classmethod
    def plugin_layer_kind(cls) -> PluginLayer:
        return PluginLayer.LOGICAL_COGNITIVE


class FunctionalPluginSpec(BasePluginSpec, ABC):
    """Atomic capability plugins that must never orchestrate other plugins."""

    @classmethod
    def plugin_layer_kind(cls) -> PluginLayer:
        return PluginLayer.FUNCTIONAL


def __getattr__(name: str) -> Any:
    """
    Backwards-compatible lazy exports.

    Some plugin implementations historically imported capability patch bases from
    `zentex.core.plugin_base`. That base now lives in `zentex.core.capability_patch_base`
    to avoid import cycles with `zentex.core.models`.
    """

    if name in {"BaseCapabilityPatchPlugin", "CapabilityPatchOutput"}:
        from zentex.core.capability_patch_base import (  # noqa: WPS433
            BaseCapabilityPatchPlugin,
            CapabilityPatchOutput,
        )

        return {
            "BaseCapabilityPatchPlugin": BaseCapabilityPatchPlugin,
            "CapabilityPatchOutput": CapabilityPatchOutput,
        }[name]
    raise AttributeError(name)
