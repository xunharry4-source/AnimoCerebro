from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus


class SensorySecurityError(RuntimeError):
    """Raised when unsafe sensory flow attempts to bypass mandatory sanitization."""


class SanitizedSignal(BaseModel):
    """Strongly typed sanitized payload required before interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    raw_fingerprint: str = Field(min_length=1)
    sanitized_text: str = Field(min_length=1)
    injection_risk: bool
    redaction_evidence: List[str] = Field(default_factory=list)


class EnvironmentEvent(BaseModel):
    """Structured event emitted into the brain after sensory interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    event_type: str = Field(min_length=1)
    source_plugin_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    risk_flags: List[str] = Field(default_factory=list)
    audit_evidence: List[str] = Field(default_factory=list)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SignalIngestPlugin(FunctionalPluginSpec, ABC):
    """Plugin contract for pulling raw external sensory signals."""

    source_kind: str = Field(min_length=1)
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN
    supports_multiple_plugins: bool = False

    @classmethod
    def plugin_kind(cls) -> str:
        return "signal_ingest"

    @abstractmethod
    def ingest_signal(self) -> str:
        """Fetch a raw external signal as an untrusted string."""


class SignalSanitizePlugin(FunctionalPluginSpec, ABC):
    """Plugin contract for transforming raw text into a safe typed signal."""

    sanitizer_name: str = Field(min_length=1)
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN
    supports_multiple_plugins: bool = False

    @classmethod
    def plugin_kind(cls) -> str:
        return "signal_sanitize"

    @abstractmethod
    def sanitize_signal(self, raw_signal: str) -> SanitizedSignal:
        """Redact or quarantine untrusted raw signal text."""


class SignalInterpretPlugin(FunctionalPluginSpec, ABC):
    """Plugin contract for translating sanitized signals into environment events."""

    interpreter_domain: str = Field(min_length=1)
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN
    supports_multiple_plugins: bool = False

    @classmethod
    def plugin_kind(cls) -> str:
        return "signal_interpret"

    @abstractmethod
    def interpret_signal(self, signal: SanitizedSignal) -> EnvironmentEvent:
        """Interpret a sanitized signal into a structured environment event."""
