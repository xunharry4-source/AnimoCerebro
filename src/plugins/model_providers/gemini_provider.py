from __future__ import annotations

import json
import os
import socket
from typing import Any, Dict, List
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import Field

from zentex.core.model_provider_spec import (
    ModelProviderAuthError,
    ModelProviderCallerContext,
    ModelProviderConfigError,
    ModelProviderHealthError,
    ModelProviderParseError,
    ModelProviderRateLimitError,
    ModelProviderRemoteError,
    ModelProviderSpec,
    ModelProviderTimeoutError,
)
from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus


class GoogleGeminiClient:
    """Low-level Gemini HTTP client used by the provider plugin."""

    def __init__(self, api_base: str, api_key: str, timeout_seconds: float) -> None:
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def generate_content(
        self,
        *,
        model: str,
        prompt: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": self._build_prompt(prompt=prompt, context=context),
                        }
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
            },
        }
        return self._post_json(
            url=f"{self._api_base}/models/{model}:generateContent",
            payload=request_payload,
        )

    def probe_model(self, *, model: str) -> Dict[str, Any]:
        return self._post_json(
            url=f"{self._api_base}/models/{model}:generateContent",
            payload={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": 'Respond with {"status":"ok"}'}],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 16,
                    "temperature": 0,
                },
            },
        )

    def _post_json(self, *, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_obj = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-goog-api-key": self._api_key,
            },
            method="POST",
        )

        with urllib_request.urlopen(request_obj, timeout=self._timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
        parsed = json.loads(raw_body)
        if not isinstance(parsed, dict):
            raise ValueError("Gemini returned a non-object JSON payload")
        return parsed

    def _build_prompt(self, *, prompt: str, context: Dict[str, Any]) -> str:
        return "\n\n".join(
            [
                "Return only valid JSON.",
                f"Prompt:\n{prompt}",
                f"Context JSON:\n{json.dumps(context, ensure_ascii=False)}",
            ]
        )


class GeminiProvider(ModelProviderSpec):
    """
    Live Gemini provider plugin under Zentex plugin-lifecycle constraints.

    Fail-closed requirement:
    - no local rule fallback
    - no empty dict / None fallback
    - every remote failure becomes a structured provider exception
    """

    provider_name: str = "gemini"
    api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    api_key_env: str = "GEMINI_API_KEY"
    default_model: str = "gemini-1.5-flash"
    timeout_seconds: float = Field(default=30.0, gt=0)
    health_probe_endpoint: str = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    health_status: PluginHealthStatus = PluginHealthStatus.UNKNOWN

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._client = GoogleGeminiClient(
            api_base=self.api_base,
            api_key=self._resolve_api_key(),
            timeout_seconds=self.timeout_seconds,
        )

    def generate_json(
        self,
        prompt: str,
        context: Dict[str, Any],
        caller_context: ModelProviderCallerContext,
    ) -> Dict[str, Any]:
        if not prompt or not prompt.strip():
            raise ModelProviderConfigError("prompt must not be empty")
        if not isinstance(caller_context, ModelProviderCallerContext):
            raise ModelProviderConfigError("caller_context must be a ModelProviderCallerContext")

        payload = self._invoke_remote(
            action="generate_json",
            request_fn=lambda: self._client.generate_content(
                model=self.default_model,
                prompt=prompt,
                context=context,
            ),
        )
        return self._extract_json_object(payload, source="generate_json")

    def health_probe(self) -> PluginHealthStatus:
        try:
            payload = self._invoke_remote(
                action="health_probe",
                request_fn=lambda: self._client.probe_model(model=self.default_model),
            )
            self._extract_json_object(payload, source="health_probe")
        except ModelProviderRateLimitError:
            return PluginHealthStatus.DEGRADED
        except ModelProviderAuthError as exc:
            raise ModelProviderHealthError(
                f"Gemini health probe authentication failed: {exc}"
            ) from exc
        except ModelProviderTimeoutError as exc:
            return PluginHealthStatus.UNHEALTHY
        except ModelProviderRemoteError as exc:
            return PluginHealthStatus.UNHEALTHY
        except ModelProviderParseError as exc:
            raise ModelProviderHealthError(
                f"Gemini health probe returned invalid JSON: {exc}"
            ) from exc

        return PluginHealthStatus.HEALTHY

    def _resolve_api_key(self) -> str:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise ModelProviderConfigError(
                f"Missing API key for Gemini provider: {self.api_key_env}"
            )
        return api_key

    def _invoke_remote(
        self,
        *,
        action: str,
        request_fn: callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            return request_fn()
        except urllib_error.HTTPError as exc:
            raise self._classify_http_error(exc, action=action) from exc
        except (urllib_error.URLError, TimeoutError, socket.timeout) as exc:
            raise ModelProviderTimeoutError(
                f"Gemini {action} timed out or lost connectivity; source=urllib"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ModelProviderParseError(
                f"Gemini {action} returned invalid JSON; source=remote_response"
            ) from exc
        except ValueError as exc:
            raise ModelProviderParseError(
                f"Gemini {action} returned invalid payload shape; source=remote_response"
            ) from exc

    def _classify_http_error(
        self,
        exc: urllib_error.HTTPError,
        *,
        action: str,
    ) -> Exception:
        status_code = getattr(exc, "code", 0)
        if status_code in {401, 403}:
            return ModelProviderAuthError(
                f"Gemini {action} authentication failed with status {status_code}; source=http"
            )
        if status_code == 429:
            return ModelProviderRateLimitError(
                f"Gemini {action} was rate limited with status 429; source=http"
            )
        return ModelProviderRemoteError(
            f"Gemini {action} remote failure with status {status_code}; source=http"
        )

    def _extract_json_object(
        self,
        payload: Dict[str, Any],
        *,
        source: str,
    ) -> Dict[str, Any]:
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ModelProviderParseError(
                f"Gemini {source} response missing candidates; source=provider_payload"
            )

        text_parts: List[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text)

        if not text_parts:
            raise ModelProviderParseError(
                f"Gemini {source} response did not include textual JSON content; source=provider_payload"
            )

        text_payload = "\n".join(text_parts)
        try:
            structured = json.loads(text_payload)
        except json.JSONDecodeError as exc:
            raise ModelProviderParseError(
                f"Gemini {source} returned invalid JSON text; source=provider_text"
            ) from exc

        if not isinstance(structured, dict):
            raise ModelProviderParseError(
                f"Gemini {source} returned non-object JSON text; source=provider_text"
            )

        return structured


def build_default_gemini_provider() -> GeminiProvider:
    return GeminiProvider(
        plugin_id="gemini-provider",
        version="1.0.0",
        is_concurrency_safe=True,
        status=PluginLifecycleStatus.CANDIDATE,
        rollback_conditions=["provider_timeout_spike", "provider_auth_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )
