"""Fail-closed HTTP JSON ModelProvider runtime for live LLM integrations."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.specs.model_provider import (
    ModelProviderAuthError,
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderTimeoutError,
)


class ProviderEndpointConfig(BaseModel):
    """Runtime configuration for one remote provider endpoint."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(default_factory=lambda: f"provider-{uuid4().hex[:12]}")
    provider_name: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    health_endpoint: str | None = None
    timeout_seconds: float = Field(default=5.0, gt=0)
    health_cache_ttl_seconds: float = Field(default=30.0, gt=0)


class ProviderHealthStatus(BaseModel):
    """Cached health probe result for a provider."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str
    available: bool
    checked_at: datetime
    classification: str
    detail: str = ""
    cached: bool = False


class ModelProviderCallRecord(BaseModel):
    """Audit record for one ModelProvider invocation."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(default_factory=lambda: f"llm-call-{uuid4().hex[:12]}")
    provider_id: str
    provider_name: str
    model: str
    prompt: str
    caller_context: dict[str, Any]
    status: str
    classification: str
    output: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LLMTransport:
    """HTTP JSON transport with explicit provider error classification."""

    def post_json(self, config: ProviderEndpointConfig, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a JSON payload to the configured provider endpoint."""

        if not config.api_key:
            raise ModelProviderConfigError("Provider API key is required")
        request = urllib_request.Request(
            config.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            self._raise_http_error(config, exc)
        except urllib_error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason).lower():
                raise ModelProviderTimeoutError(f"{config.provider_name} timeout") from exc
            raise ModelProviderRemoteError(f"{config.provider_name} remote failure: {reason}") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ModelProviderTimeoutError(f"{config.provider_name} timeout") from exc
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelProviderParseError("invalid_json") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderParseError("invalid_json")
        return decoded

    def get_json(self, config: ProviderEndpointConfig, url: str) -> dict[str, Any]:
        """GET provider health JSON with the same auth contract."""

        request = urllib_request.Request(
            url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            method="GET",
        )
        try:
            with urllib_request.urlopen(request, timeout=config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            self._raise_http_error(config, exc)
        except Exception as exc:
            raise ModelProviderRemoteError(f"{config.provider_name} health probe failed: {exc}") from exc
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelProviderParseError("invalid_json") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderParseError("invalid_json")
        return decoded

    def _raise_http_error(self, config: ProviderEndpointConfig, exc: urllib_error.HTTPError) -> None:
        status = int(getattr(exc, "code", 0) or 0)
        if status in {401, 403}:
            raise ModelProviderAuthError("auth_failed") from exc
        if status == 429:
            raise ModelProviderRateLimitError("rate_limited") from exc
        raise ModelProviderRemoteError(f"{config.provider_name} remote status {status}") from exc


@dataclass
class HTTPJSONModelProvider:
    """ModelProvider plugin implementation backed by real HTTP JSON calls."""

    config: ProviderEndpointConfig
    transport: LLMTransport = field(default_factory=LLMTransport)
    _health_status: ProviderHealthStatus | None = None

    @property
    def plugin_id(self) -> str:
        """Return the provider id used by the ModelProvider contract."""

        return self.config.provider_id

    def generate_json(
        self,
        *,
        prompt: str,
        context: dict[str, Any],
        caller_context: ModelProviderCallerContext | dict[str, Any] | Any,
    ) -> dict[str, Any]:
        """Generate one JSON object through the remote provider."""

        caller_payload = (
            caller_context.model_dump(mode="json")
            if hasattr(caller_context, "model_dump")
            else dict(caller_context or {})
        )
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "context": context,
            "caller_context": caller_payload,
            "response_format": "json_object",
        }
        response = self.transport.post_json(self.config, payload)
        return self._extract_json(response)

    def health_probe(self) -> ProviderHealthStatus:
        """Probe provider health and cache the result for the configured TTL."""

        now = datetime.now(timezone.utc)
        if self._health_status is not None:
            age = (now - self._health_status.checked_at).total_seconds()
            if age <= self.config.health_cache_ttl_seconds:
                return self._health_status.model_copy(update={"cached": True})
        try:
            if self.config.health_endpoint:
                payload = self.transport.get_json(self.config, self.config.health_endpoint)
            else:
                payload = self.transport.post_json(self.config, {"model": self.config.model, "health_probe": True})
            available = bool(payload.get("ok", payload.get("available", True)))
            status = ProviderHealthStatus(
                provider_id=self.config.provider_id,
                available=available,
                checked_at=now,
                classification="available" if available else "remote_failed",
                detail=str(payload.get("detail", "")),
            )
        except Exception as exc:
            status = ProviderHealthStatus(
                provider_id=self.config.provider_id,
                available=False,
                checked_at=now,
                classification=classify_provider_error(exc),
                detail=str(exc),
            )
        self._health_status = status
        return status

    @staticmethod
    def _extract_json(response: dict[str, Any]) -> dict[str, Any]:
        if isinstance(response.get("json"), dict):
            return response["json"]
        text = response.get("output_text")
        if text is None:
            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                text = ((choices[0] or {}).get("message") or {}).get("content")
        if not str(text or "").strip():
            raise ModelProviderParseError("empty_result")
        try:
            parsed = json.loads(str(text))
        except json.JSONDecodeError as exc:
            raise ModelProviderParseError("invalid_json") from exc
        if not isinstance(parsed, dict):
            raise ModelProviderParseError("invalid_json")
        return parsed


def classify_provider_error(exc: BaseException) -> str:
    """Map provider exceptions to the G28 public classification matrix."""

    if isinstance(exc, ModelProviderConfigError):
        return "missing_api_key"
    if isinstance(exc, ModelProviderAuthError):
        return "auth_failed"
    if isinstance(exc, ModelProviderRateLimitError):
        return "rate_limited"
    if isinstance(exc, ModelProviderTimeoutError):
        return "timeout"
    if isinstance(exc, ModelProviderParseError):
        text = str(exc)
        return text if text in {"invalid_json", "empty_result"} else "invalid_json"
    return "remote_failed"


class ModelProviderRuntime:
    """Registry and audit ledger for active HTTP JSON ModelProvider plugins."""

    def __init__(self) -> None:
        self._providers: dict[str, HTTPJSONModelProvider] = {}
        self._calls: dict[str, ModelProviderCallRecord] = {}

    def register_provider(self, config: ProviderEndpointConfig) -> ProviderEndpointConfig:
        """Register a provider and return the persisted config."""

        if not config.api_key:
            raise ModelProviderConfigError("Provider API key is required")
        self._providers[config.provider_id] = HTTPJSONModelProvider(config)
        return config

    def generate_json(
        self,
        provider_id: str,
        *,
        prompt: str,
        context: dict[str, Any],
        caller_context: dict[str, Any],
    ) -> ModelProviderCallRecord:
        """Invoke a provider and persist the exact call result or failure."""

        provider = self._providers.get(provider_id)
        if provider is None:
            raise ModelProviderConfigError(f"Unknown provider: {provider_id}")
        try:
            output = provider.generate_json(
                prompt=prompt,
                context=context,
                caller_context=caller_context,
            )
            record = ModelProviderCallRecord(
                provider_id=provider_id,
                provider_name=provider.config.provider_name,
                model=provider.config.model,
                prompt=prompt,
                caller_context=caller_context,
                status="succeeded",
                classification="ok",
                output=output,
            )
        except Exception as exc:
            record = ModelProviderCallRecord(
                provider_id=provider_id,
                provider_name=provider.config.provider_name,
                model=provider.config.model,
                prompt=prompt,
                caller_context=caller_context,
                status="failed",
                classification=classify_provider_error(exc),
                error=str(exc),
            )
            self._calls[record.call_id] = record
            raise
        self._calls[record.call_id] = record
        return record

    def health_probe(self, provider_id: str) -> ProviderHealthStatus:
        """Return cached or fresh provider health."""

        provider = self._providers.get(provider_id)
        if provider is None:
            raise ModelProviderConfigError(f"Unknown provider: {provider_id}")
        return provider.health_probe()

    def get_call(self, call_id: str) -> ModelProviderCallRecord | None:
        """Return a stored call record."""

        return self._calls.get(call_id)

    def list_calls(self) -> list[ModelProviderCallRecord]:
        """Return all call records in insertion order."""

        return list(self._calls.values())
