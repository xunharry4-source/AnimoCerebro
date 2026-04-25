"""
OpenAI provider adapters.

Covers:
- OpenAITool          — native Responses API (gpt-4.1 etc.)
- ChatGPTTool         — alias of OpenAITool for the chatgpt provider key
- OpenAICompatibleGatewayTool — OpenAI-SDK-backed adapter for any /v1-compatible gateway
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import (
    AuthError,
    BaseProviderTool,
    ConfigError,
    ProviderToolConfig,
    RateLimitError,
    RemoteServiceError,
    RemoteTimeoutError,
    ResponseParseError,
    ToolInvocationRequest,
    ToolInvocationResponse,
)

try:
    from openai import (
        APIConnectionError as OpenAIAPIConnectionError,
        APIStatusError as OpenAIAPIStatusError,
        APITimeoutError as OpenAIAPITimeoutError,
        AuthenticationError as OpenAIAuthenticationError,
        OpenAI,
        RateLimitError as OpenAIRateLimitError,
    )
except ImportError:  # pragma: no cover
    OpenAI = None
    OpenAIAPIConnectionError = None
    OpenAIAPIStatusError = None
    OpenAIAPITimeoutError = None
    OpenAIAuthenticationError = None
    OpenAIRateLimitError = None


class OpenAITool(BaseProviderTool):
    """Native OpenAI Responses API adapter."""

    def _build_url(self) -> str:
        return f"{self.config.api_base.rstrip('/')}/responses"

    def _provider_headers(self, api_key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:
        prompt = invocation.prompt
        if invocation.system_prompt:
            prompt = f"{invocation.system_prompt}\n\n{invocation.prompt}"
        return {
            "model": invocation.model,
            "input": prompt,
            "temperature": invocation.temperature,
            "max_output_tokens": invocation.max_output_tokens,
            "metadata": invocation.metadata,
        }

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        output = payload.get("output", [])
        for item in output:
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return str(content.get("text", ""))
        return str(payload.get("output_text", ""))


class ChatGPTTool(OpenAITool):
    """ChatGPT transport — same Responses contract as OpenAITool."""


class OpenAICompatibleGatewayTool:
    """
    OpenAI-SDK-backed adapter for any /v1-compatible gateway.

    Suitable for:
    - local model routers (LM Studio, Ollama /v1, etc.)
    - OpenAI-compatible proxy gateways
    - local Gemini/Claude adapters behind the OpenAI contract
    """

    def __init__(self, config: ProviderToolConfig) -> None:
        self.config = config

    @property
    def default_model(self) -> str:
        """Configured model for OpenAI-compatible gateways."""
        return str(self.config.default_model or "")

    def call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        if OpenAI is None:
            raise ConfigError("openai package is not installed in the local environment")

        from .config import resolve_provider_api_key
        api_key = resolve_provider_api_key(self.config)
        client = OpenAI(base_url=self.config.api_base, api_key=api_key)

        try:
            response = client.chat.completions.create(
                model=invocation.model,
                messages=self._build_messages(invocation),
                temperature=invocation.temperature,
            )
        except OpenAIAuthenticationError as exc:
            raise AuthError(
                f"Authentication failed for provider {self.config.provider_name}"
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                f"Rate limit exceeded for provider {self.config.provider_name}"
            ) from exc
        except (OpenAIAPITimeoutError, OpenAIAPIConnectionError) as exc:
            raise RemoteTimeoutError(
                f"Remote provider timeout or network failure for {self.config.provider_name}"
            ) from exc
        except OpenAIAPIStatusError as exc:
            raise RemoteServiceError(
                f"Remote provider {self.config.provider_name} failed with status {exc.status_code}"
            ) from exc
        except Exception as exc:
            raise RemoteServiceError(
                f"Unexpected provider failure for {self.config.provider_name}"
            ) from exc

        output_text = self._extract_text(response)
        usage = (
            response.usage.model_dump()
            if hasattr(response, "usage") and response.usage
            else None
        )
        return ToolInvocationResponse(
            provider=self.config.provider_name,
            model=invocation.model,
            output_text=output_text,
            usage=usage,
            raw_response=response.model_dump(),
        )

    def _build_messages(self, invocation: ToolInvocationRequest) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if invocation.system_prompt:
            messages.append({"role": "system", "content": invocation.system_prompt})
        messages.append({"role": "user", "content": invocation.prompt})
        return messages

    def _extract_text(self, response: Any) -> str:
        try:
            return str(response.choices[0].message.content)
        except Exception as exc:
            raise ResponseParseError(
                f"Provider {self.config.provider_name} returned an invalid SDK response shape"
            ) from exc
