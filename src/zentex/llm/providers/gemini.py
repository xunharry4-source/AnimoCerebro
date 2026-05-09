"""
Google Gemini provider adapter (google-genai SDK).
"""
from __future__ import annotations

import socket
from typing import Any, Dict, Optional

from .base import (
    AuthError,
    BaseProviderTool,
    ConfigError,
    RateLimitError,
    RemoteServiceError,
    RemoteTimeoutError,
    ToolInvocationRequest,
    ToolInvocationResponse,
)

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None


class GeminiTool(BaseProviderTool):
    """Google Gemini adapter using the official ``google-genai`` SDK."""

    def call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        if genai is None:
            raise ConfigError(
                "google-genai package is not installed in the local environment"
            )

        api_key = self._resolve_api_key()
        client = genai.Client(api_key=api_key)

        contents = invocation.prompt
        if invocation.system_prompt:
            contents = f"{invocation.system_prompt}\n\n{invocation.prompt}"

        try:
            response = client.models.generate_content(
                model=invocation.model,
                contents=contents,
            )
        except Exception as exc:
            raise self._classify_sdk_error(exc) from exc

        raw_response = self._response_to_dict(response)
        return ToolInvocationResponse(
            provider=self.config.provider_name,
            model=invocation.model,
            output_text=str(getattr(response, "text", "") or ""),
            usage=self._extract_usage(raw_response),
            raw_response=raw_response,
        )

    # ------------------------------------------------------------------
    # Error classification
    # ------------------------------------------------------------------

    def _classify_sdk_error(self, exc: Exception) -> Exception:
        status_code = getattr(exc, "status_code", None)
        if status_code in {401, 403}:
            return AuthError(
                f"Authentication failed for provider {self.config.provider_name} "
                f"with status {status_code}"
            )
        if status_code == 429:
            return RateLimitError(
                f"Rate limit exceeded for provider {self.config.provider_name}"
            )
        if status_code is not None and int(status_code) >= 500:
            return RemoteServiceError(
                f"Remote provider {self.config.provider_name} failed with status {status_code}"
            )
        message = str(exc).lower()
        if "auth" in message or "api key" in message or "permission" in message:
            return AuthError(
                f"Authentication failed for provider {self.config.provider_name}"
            )
        if "rate" in message or "quota" in message or "429" in message:
            return RateLimitError(
                f"Rate limit exceeded for provider {self.config.provider_name}"
            )
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return RemoteTimeoutError(
                f"Remote provider timeout or network failure for {self.config.provider_name}"
            )
        return RemoteTimeoutError(
            f"Remote provider timeout or network failure for {self.config.provider_name}"
        )

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _response_to_dict(self, response: Any) -> Dict[str, Any]:
        if hasattr(response, "model_dump") and callable(response.model_dump):
            dumped = response.model_dump()
            return dumped if isinstance(dumped, dict) else {"response": dumped}
        if hasattr(response, "to_dict") and callable(response.to_dict):
            dumped = response.to_dict()
            return dumped if isinstance(dumped, dict) else {"response": dumped}
        text = getattr(response, "text", None)
        usage = getattr(response, "usage_metadata", None)
        usage_dict: Optional[Dict[str, Any]] = None
        if usage is not None:
            if hasattr(usage, "model_dump") and callable(usage.model_dump):
                usage_dict = usage.model_dump()
            elif hasattr(usage, "to_dict") and callable(usage.to_dict):
                usage_dict = usage.to_dict()
        payload: Dict[str, Any] = {}
        if text is not None:
            payload["text"] = text
        if isinstance(usage_dict, dict):
            payload["usage_metadata"] = usage_dict
        return payload

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        return str(payload.get("text", "") or "")

    def _extract_usage(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        usage = payload.get("usage_metadata") or payload.get("usageMetadata")
        if not isinstance(usage, dict):
            return None
        return {
            "input_tokens": usage.get("prompt_token_count") or usage.get("promptTokenCount"),
            "output_tokens": (
                usage.get("candidates_token_count") or usage.get("candidatesTokenCount")
            ),
            "total_tokens": usage.get("total_token_count") or usage.get("totalTokenCount"),
        }

    # SDK handles HTTP — these are unreachable but satisfy the abstract interface.
    def _build_url(self) -> str:  # pragma: no cover
        raise NotImplementedError("GeminiTool uses the official google.genai SDK")

    def _provider_headers(self, api_key: str) -> Dict[str, str]:  # pragma: no cover
        raise NotImplementedError("GeminiTool uses the official google.genai SDK")

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError("GeminiTool uses the official google.genai SDK")
