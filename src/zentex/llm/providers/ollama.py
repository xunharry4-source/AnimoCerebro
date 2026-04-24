"""
Ollama local provider adapter.

- Queries /api/tags at startup to resolve the best available model dynamically.
- Uses /api/chat (modern Ollama contract, works with all model families).
- No API key required.
"""
from __future__ import annotations

import json
import logging
import socket
from typing import Any, Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from .base import (
    BaseProviderTool,
    ProviderToolConfig,
    RemoteServiceError,
    RemoteTimeoutError,
    ResponseParseError,
    ToolInvocationRequest,
    ToolInvocationResponse,
)

logger = logging.getLogger(__name__)


def resolve_ollama_model(api_base: str, preferred: str) -> tuple[str, list[str]]:
    """Query ``/api/tags`` and return (best_available_model, all_available_models).

    Priority:
    1. ``preferred`` — if it exists in the local library
    2. First model in the list (most recently modified)
    3. ``preferred`` as-is — if Ollama is unreachable at startup time

    The second element of the tuple is the full list so callers can include
    it in error messages to help the user choose a valid model name.
    """
    try:
        tags_url = f"{api_base.rstrip('/')}/api/tags"
        req = urllib_request.Request(tags_url, method="GET")
        with urllib_request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        models: list[str] = [
            str(m.get("name") or "").strip()
            for m in (data.get("models") or [])
            if m.get("name")
        ]
        if not models:
            return preferred, []
        if preferred in models:
            return preferred, models

        logger.info(
            "Ollama: configured model '%s' not found locally; using '%s' instead. "
            "Available: %s",
            preferred,
            models[0],
            ", ".join(models),
        )
        return models[0], models
    except Exception:
        # Ollama not reachable yet — fall back silently.
        logger.debug("resolve_ollama_model: /api/tags unreachable, keeping preferred=%r", preferred, exc_info=True)
        return preferred, []


class OllamaTool(BaseProviderTool):
    """Native Ollama transport using the local ``/api/generate`` contract."""

    def __init__(self, config: ProviderToolConfig) -> None:
        super().__init__(config)
        # Resolve the best available model once at startup.
        self._resolved_model, _ = resolve_ollama_model(
            config.api_base, str(config.default_model or "")
        )

    @property
    def default_model(self) -> str:
        """Dynamically resolved model name (set once at init from /api/tags)."""
        return self._resolved_model

    def call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        logger.info(
            "OllamaTool.call: model=%r  url=%s",
            invocation.model,
            self._build_url(),
        )
        try:
            return self._do_call(invocation)
        except RemoteServiceError as exc:
            # Ollama returns 404 when the model name is not found locally.
            # This can happen if the process started before the model was
            # available, or before the YAML was updated.  Re-resolve from
            # /api/tags and retry once with the corrected name.
            if "404" not in str(exc):
                raise
            logger.warning(
                "OllamaTool: got 404 for model %r — re-resolving from /api/tags …",
                invocation.model,
            )
            fresh_model, available_models = resolve_ollama_model(
                self.config.api_base, str(self.config.default_model or "")
            )
            if fresh_model == invocation.model:
                # Model is still not found after re-resolve.  Give an
                # actionable error instead of re-raising the raw HTTP body.
                if available_models:
                    available_hint = (
                        f"Available models: {', '.join(available_models)}.\n"
                        f"  Update config/provider_tools.yml → ollama.default_model "
                        f"to one of the above, or run: ollama pull {fresh_model}"
                    )
                else:
                    available_hint = (
                        f"Ollama has no models pulled yet.\n"
                        f"  Run: ollama pull {fresh_model}"
                    )
                logger.error(
                    "OllamaTool: model '%s' not found in Ollama. %s",
                    fresh_model, available_hint,
                )
                raise RemoteServiceError(
                    f"Ollama model '{fresh_model}' is not available. {available_hint}"
                ) from exc
            logger.info(
                "OllamaTool: retrying with fresh model %r (was %r)",
                fresh_model,
                invocation.model,
            )
            self._resolved_model = fresh_model
            fresh_invocation = ToolInvocationRequest(
                model=fresh_model,
                prompt=invocation.prompt,
                system_prompt=invocation.system_prompt,
                temperature=invocation.temperature,
                max_output_tokens=invocation.max_output_tokens,
                metadata=invocation.metadata,
            )
            return self._do_call(fresh_invocation)

    def _do_call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        timeout_seconds = float(self.config.timeout_seconds)
        requested_timeout = invocation.metadata.get("request_timeout_seconds")
        if requested_timeout is not None:
            try:
                timeout_seconds = max(1.0, min(timeout_seconds, float(requested_timeout)))
            except Exception:
                logger.exception(
                    "OllamaTool: invalid request_timeout_seconds=%r; using default timeout %.1fs",
                    requested_timeout,
                    timeout_seconds,
                )
        req = urllib_request.Request(
            url=self._build_url(),
            data=json.dumps(self._build_payload(invocation)).encode("utf-8"),
            headers=self._build_headers(""),   # Ollama needs no auth header
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            raise self._classify_http_error(exc) from exc
        except urllib_error.URLError as exc:
            reason = getattr(exc, "reason", None)
            reason_text = str(reason or exc).strip()
            if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in reason_text.lower():
                logger.error(
                    "Ollama request timeout | provider=%s model=%s timeout=%.1fs reason=%s",
                    self.config.provider_name,
                    invocation.model,
                    timeout_seconds,
                    reason_text or type(exc).__name__,
                )
                raise RemoteTimeoutError(
                    f"{self.config.provider_name} timeout after {timeout_seconds:.1f}s: {reason_text or type(exc).__name__}"
                ) from exc
            logger.error(
                "Ollama network failure | provider=%s model=%s timeout=%.1fs reason_type=%s reason=%s",
                self.config.provider_name,
                invocation.model,
                timeout_seconds,
                type(reason).__name__ if reason is not None else type(exc).__name__,
                reason_text or "unknown",
            )
            raise RemoteServiceError(
                f"{self.config.provider_name} network failure: {reason_text or type(exc).__name__}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            logger.error(
                "Ollama request timeout | provider=%s model=%s timeout=%.1fs reason=%s",
                self.config.provider_name,
                invocation.model,
                timeout_seconds,
                str(exc) or type(exc).__name__,
            )
            raise RemoteTimeoutError(
                f"{self.config.provider_name} timeout after {timeout_seconds:.1f}s: {str(exc) or type(exc).__name__}"
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

    def _build_url(self) -> str:
        # /api/chat is the modern Ollama endpoint — supported by all model families
        # (including multimodal/reasoning models like gemma4, llava, deepseek-r1).
        return f"{self.config.api_base.rstrip('/')}/api/chat"

    def _provider_headers(self, api_key: str) -> Dict[str, str]:
        return {}   # Ollama requires no authentication headers

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:
        messages = []
        if invocation.system_prompt:
            messages.append({"role": "system", "content": invocation.system_prompt})
        messages.append({"role": "user", "content": invocation.prompt})
        payload: Dict[str, Any] = {
            "model": invocation.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": invocation.temperature,
                "num_predict": invocation.max_output_tokens,
            },
        }
        # Only enforce JSON mode when the caller explicitly opted in via metadata.
        # Unconditionally setting format="json" causes Ollama to reject responses
        # from models that output natural language (e.g. reasoning steps), and
        # also causes 400/422 errors on models that do not support structured output.
        if invocation.metadata.get("require_json_format"):
            payload["format"] = "json"
        return payload

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        # /api/chat response: {"message": {"role": "assistant", "content": "..."}}
        message = payload.get("message") or {}
        if isinstance(message, dict):
            return str(message.get("content", "") or "")
        return ""

    def _extract_usage(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        input_tokens = int(payload.get("prompt_eval_count") or 0)
        output_tokens = int(payload.get("eval_count") or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
