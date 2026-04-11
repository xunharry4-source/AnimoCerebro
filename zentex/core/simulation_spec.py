from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus


class SimulationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    intent_name: str = Field(min_length=1)
    target_domain: str = Field(min_length=1)
    intent_payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = Field(min_length=1)


class SimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    is_safe: bool
    predicted_impacts: list[str] = Field(default_factory=list)
    veto_reason: str | None = None
    replan_required: bool
    simulated_by: str = Field(min_length=1)
    fallback_used: bool = False
    simulated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SimulationDomainPlugin(FunctionalPluginSpec, ABC):
    supported_domains: list[str] = Field(min_length=1)
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN
    supports_multiple_plugins: bool = False

    @classmethod
    def plugin_kind(cls) -> str:
        return "simulation_domain"

    @abstractmethod
    def simulate_action(
        self,
        intent: SimulationIntent,
        context: dict[str, Any],
    ) -> SimulationResult:
        """
        Run a no-side-effects prediction over an intent.

        Simulation plugins must never call execution plugins or produce real
        physical side effects.
        """
