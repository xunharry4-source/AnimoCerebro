from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from zentex.core.plugin_base import FunctionalPluginSpec, PluginHealthStatus


class ModelProviderError(RuntimeError):
    """Base failure for live model-provider calls."""


class ModelProviderConfigError(ModelProviderError):
    """Raised when required local provider configuration is missing or invalid."""


class ModelProviderAuthError(ModelProviderError):
    """Raised when credentials are missing or rejected by the remote provider."""


class ModelProviderTimeoutError(ModelProviderError):
    """Raised when the remote provider times out or becomes unreachable."""


class ModelProviderRateLimitError(ModelProviderError):
    """Raised when the provider rejects the request due to quota or rate limiting."""


class ModelProviderRemoteError(ModelProviderError):
    """Raised when the provider returns a non-auth, non-rate-limited failure."""


class ModelProviderParseError(ModelProviderError):
    """Raised when provider output is not valid JSON for structured reasoning."""


class ModelProviderHealthError(ModelProviderError):
    """Raised when a health probe cannot determine provider health safely."""


class ModelProviderCallerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    source_module: str = Field(min_length=1)
    invocation_phase: str = Field(min_length=1)
    question_driver_refs: List[str] = Field(default_factory=list)
    decision_id: Optional[str] = None
    trace_id: Optional[str] = None


class ModelProviderSpec(FunctionalPluginSpec, ABC):
    """
    Unified contract for live LLM provider plugins.

    Mandatory capabilities:
    - structured JSON generation for reasoning
    - explicit health probe surface
    - visible health state for runtime isolation and degrade decisions
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        use_enum_values=False,
        str_strip_whitespace=True,
    )

    provider_name: str = Field(min_length=1)
    api_base: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    default_model: str = Field(min_length=1)
    supports_multiple_plugins: bool = False
    timeout_seconds: float = Field(default=30.0, gt=0)
    health_probe_endpoint: str = Field(min_length=1)
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN

    @classmethod
    def plugin_kind(cls) -> str:
        return "model_provider"

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
        *,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a live LLM request and return a parsed JSON object.

        Fail-closed rule:
        - never return a fake fallback object on provider failure
        - always raise a structured provider exception instead
        - caller identity and question-driver provenance are mandatory
        """

    @abstractmethod
    def health_probe(self) -> PluginHealthStatus:
        """
        Probe live provider connectivity and quota posture.

        The implementation must reflect real remote state instead of static flags.
        """
