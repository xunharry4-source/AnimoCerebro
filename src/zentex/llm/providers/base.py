"""
Base models, error types, and abstract transport for all LLM provider adapters.
"""
from __future__ import annotations

import json
import socket
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel, ConfigDict, Field
from zentex.launcher.config import CONFIG_DIR
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEFAULT_PROVIDER_CONFIG_PATH = CONFIG_DIR / "provider_tools.yml"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProviderToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    provider_name: str = Field(min_length=1)
    api_base: str = Field(min_length=1)
    api_key_env: Optional[str] = Field(default=None)
    default_model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=30.0, gt=0)


class ToolInvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    system_prompt: Optional[str] = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, gt=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolInvocationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str
    output_text: str
    usage: Optional[Dict[str, Any]] = None
    raw_response: Dict[str, Any]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ModelProviderError(RuntimeError):
    """Base failure for provider-tool invocations."""


class ConfigError(ModelProviderError):
    """Raised when required local provider configuration is missing."""


class AuthError(ModelProviderError):
    """Raised when credentials are missing or rejected by the remote provider."""


class RemoteTimeoutError(ModelProviderError):
    """Raised when the remote provider times out or the network stalls."""


class RemoteServiceError(ModelProviderError):
    """Raised when the remote provider returns a server-side failure."""


class RateLimitError(ModelProviderError):
    """Raised when the provider rejects the request due to quota or rate limit."""


class ResponseParseError(ModelProviderError):
    """Raised when the provider returns invalid or non-conforming JSON."""


# ---------------------------------------------------------------------------
# Base transport
# ---------------------------------------------------------------------------

class BaseProviderTool:
    """Shared HTTP transport wrapper for provider-specific adapters."""

    def __init__(self, config: ProviderToolConfig) -> None:
        self.config = config

    @property
    def default_model(self) -> str:
        """Configured default model for providers that do not override it."""
        return str(self.config.default_model or "")

    def call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        api_key = self._resolve_api_key()
        req = urllib_request.Request(
            url=self._build_url(),
            data=json.dumps(self._build_payload(invocation)).encode("utf-8"),
            headers=self._build_headers(api_key),
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            raise self._classify_http_error(exc) from exc
        except urllib_error.URLError as exc:
            reason = getattr(exc, "reason", None)
            reason_text = str(reason or exc).strip()
            if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in reason_text.lower():
                logger.error(
                    "Provider timeout | provider=%s model=%s timeout=%.1fs reason=%s",
                    self.config.provider_name,
                    invocation.model,
                    float(self.config.timeout_seconds),
                    reason_text or type(exc).__name__,
                )
                raise RemoteTimeoutError(
                    f"{self.config.provider_name} timeout after {float(self.config.timeout_seconds):.1f}s: {reason_text or type(exc).__name__}"
                ) from exc
            logger.error(
                "Provider network failure | provider=%s model=%s timeout=%.1fs reason_type=%s reason=%s",
                self.config.provider_name,
                invocation.model,
                float(self.config.timeout_seconds),
                type(reason).__name__ if reason is not None else type(exc).__name__,
                reason_text or "unknown",
            )
            raise RemoteServiceError(
                f"{self.config.provider_name} network failure: {reason_text or type(exc).__name__}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            logger.error(
                "Provider timeout | provider=%s model=%s timeout=%.1fs reason=%s",
                self.config.provider_name,
                invocation.model,
                float(self.config.timeout_seconds),
                str(exc) or type(exc).__name__,
            )
            raise RemoteTimeoutError(
                f"{self.config.provider_name} timeout after {float(self.config.timeout_seconds):.1f}s: {str(exc) or type(exc).__name__}"
            ) from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ResponseParseError(
                f"Provider {self.config.provider_name} returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise ResponseParseError(
                f"Provider {self.config.provider_name} returned a non-object JSON payload"
            )

        return ToolInvocationResponse(
            provider=self.config.provider_name,
            model=invocation.model,
            output_text=self._extract_text(payload),
            usage=self._extract_usage(payload),
            raw_response=payload,
        )

    def _extract_usage(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return payload.get("usage")

    def _resolve_api_key(self) -> str:
        from .config import resolve_provider_api_key
        return resolve_provider_api_key(self.config)

    def _classify_http_error(self, exc: urllib_error.HTTPError) -> ModelProviderError:
        status_code = getattr(exc, "code", 0)
        # Try to read the response body for a richer error message.
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        detail = f" — {body}" if body else ""

        if status_code in {401, 403}:
            return AuthError(
                f"Authentication failed for provider {self.config.provider_name} "
                f"with status {status_code}{detail}"
            )
        if status_code == 429:
            return RateLimitError(
                f"Rate limit exceeded for provider {self.config.provider_name}{detail}"
            )
        return RemoteServiceError(
            f"Remote provider {self.config.provider_name} failed with status {status_code}{detail}"
        )

    def _build_headers(self, api_key: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            **self._provider_headers(api_key),
        }

    def _build_url(self) -> str:
        raise NotImplementedError

    def _provider_headers(self, api_key: str) -> Dict[str, str]:
        raise NotImplementedError

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:
        raise NotImplementedError

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        raise NotImplementedError
