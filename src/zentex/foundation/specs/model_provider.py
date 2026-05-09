from __future__ import annotations

from typing import Any, Protocol, runtime_checkable, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ModelProviderCallerContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_module: str
    invocation_phase: str
    question_driver_refs: list[str] = Field(default_factory=list)
    decision_id: Optional[str] = None
    trace_id: Optional[str] = None


@runtime_checkable
class ModelProviderSpec(Protocol):
    plugin_id: str

    def generate_json(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        caller_context: Union[ModelProviderCallerContext, dict[str], Any],
        max_output_tokens: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]: ...


class ModelProviderError(RuntimeError):
    """Base exception for all model provider errors.
    
    This is the parent class for all specific provider error types.
    Catch this to handle any provider-related error.
    """
    pass


class ModelProviderRemoteError(ModelProviderError):
    """Error communicating with remote model provider service."""
    pass


class ModelProviderParseError(ModelProviderError):
    """Error parsing model provider response."""
    pass


class ModelProviderHealthError(ModelProviderError):
    """Error checking model provider health status."""
    pass


class ModelProviderTimeoutError(ModelProviderError):
    """Model provider request timed out."""
    pass


class ModelProviderRateLimitError(ModelProviderError):
    """Model provider rate limit exceeded."""
    pass


class ModelProviderAuthError(ModelProviderError):
    """Model provider authentication failed."""
    pass


class ModelProviderConfigError(ModelProviderError):
    """Model provider configuration error."""
    pass
