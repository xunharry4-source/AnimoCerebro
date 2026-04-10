from __future__ import annotations

"""
Tool methods for external LLM providers.

These adapters are plain tool-method wrappers around provider HTTP contracts.
They are intentionally not plugin lifecycle models. Their job is only to:

- build provider-specific request payloads
- attach authentication headers
- normalize text output
"""

import functools
import json
import os
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel, ConfigDict, Field
from zentex.core.config import CONFIG_DIR, load_required_mapping_section, load_yaml_config

try:
    from openai import (
        APIConnectionError as OpenAIAPIConnectionError,
        APIStatusError as OpenAIAPIStatusError,
        APITimeoutError as OpenAIAPITimeoutError,
        AuthenticationError as OpenAIAuthenticationError,
        OpenAI,
        RateLimitError as OpenAIRateLimitError,
    )
except ImportError:  # pragma: no cover - exercised through runtime config checks
    OpenAI = None
    OpenAIAPIConnectionError = None
    OpenAIAPIStatusError = None
    OpenAIAPITimeoutError = None
    OpenAIAuthenticationError = None
    OpenAIRateLimitError = None


class ProviderToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    provider_name: str = Field(min_length=1)
    api_base: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
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


DEFAULT_PROVIDER_CONFIG_PATH = CONFIG_DIR / "provider_tools.yml"


class BaseProviderTool:
    """Shared transport wrapper for provider-specific tool methods."""

    def __init__(self, config: ProviderToolConfig) -> None:
        self.config = config

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
        except (urllib_error.URLError, TimeoutError, socket.timeout) as exc:
            raise RemoteTimeoutError(
                f"Remote provider timeout or network failure for {self.config.provider_name}"
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
        """Extract token usage details from the provider response payload."""
        return payload.get("usage")

    def _resolve_api_key(self) -> str:
        return resolve_provider_api_key(self.config)

    def _classify_http_error(self, exc: urllib_error.HTTPError) -> ModelProviderError:
        status_code = getattr(exc, "code", 0)
        if status_code in {401, 403}:
            return AuthError(
                f"Authentication failed for provider {self.config.provider_name} with status {status_code}"
            )
        if status_code == 429:
            return RateLimitError(
                f"Rate limit exceeded for provider {self.config.provider_name}"
            )
        return RemoteServiceError(
            f"Remote provider {self.config.provider_name} failed with status {status_code}"
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


class OpenAITool(BaseProviderTool):
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
    """ChatGPT transport tool built on the same OpenAI Responses contract."""


class GeminiTool(BaseProviderTool):
    def _build_url(self) -> str:
        return (
            f"{self.config.api_base.rstrip('/')}/models/"
            f"{self.config.default_model}:generateContent"
        )

    def _provider_headers(self, api_key: str) -> Dict[str, str]:
        return {"x-goog-api-key": api_key}

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:
        contents = []
        if invocation.system_prompt:
            contents.append({"role": "user", "parts": [{"text": invocation.system_prompt}]})
        contents.append({"role": "user", "parts": [{"text": invocation.prompt}]})
        return {
            "contents": contents,
            "generationConfig": {
                "temperature": invocation.temperature,
                "maxOutputTokens": invocation.max_output_tokens,
            },
        }

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        candidates = payload.get("candidates", [])
        for candidate in candidates:
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                text = part.get("text")
                if text:
                    return str(text)
        return ""

    def _extract_usage(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        usage = payload.get("usageMetadata")
        if not usage:
            return None
        return {
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        }


class ClaudeTool(BaseProviderTool):
    def _build_url(self) -> str:
        return f"{self.config.api_base.rstrip('/')}/messages"

    def _provider_headers(self, api_key: str) -> Dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": invocation.model,
            "max_tokens": invocation.max_output_tokens,
            "temperature": invocation.temperature,
            "messages": [{"role": "user", "content": invocation.prompt}],
        }
        if invocation.system_prompt:
            payload["system"] = invocation.system_prompt
        return payload

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        content = payload.get("content", [])
        for item in content:
            if item.get("type") == "text":
                return str(item.get("text", ""))
        return ""

    def _extract_usage(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        usage = payload.get("usage")
        if not usage:
            return None
        return {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }


class OpenAICompatibleGatewayTool:
    """
    Tool wrapper for local or remote OpenAI-compatible gateways.

    This path is intended for setups such as:
    - local model routers exposing `/v1`
    - OpenAI-compatible proxy gateways
    - local Gemini/Claude adapters fronted behind the OpenAI SDK contract
    """

    def __init__(self, config: ProviderToolConfig) -> None:
        self.config = config

    def call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        if OpenAI is None:
            raise ConfigError(
                "openai package is not installed in the local environment"
            )

        api_key = self._resolve_api_key()
        client = OpenAI(
            base_url=self.config.api_base,
            api_key=api_key,
        )

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
        usage = response.usage.model_dump() if hasattr(response, "usage") and response.usage else None
        return ToolInvocationResponse(
            provider=self.config.provider_name,
            model=invocation.model,
            output_text=output_text,
            usage=usage,
            raw_response=response.model_dump(),
        )

    def _resolve_api_key(self) -> str:
        return resolve_provider_api_key(self.config)

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


@functools.lru_cache(maxsize=1)
def load_provider_tool_configs(
    config_path: Union[str, os.PathLike[str]] = DEFAULT_PROVIDER_CONFIG_PATH,
) -> Dict[str, ProviderToolConfig]:
    try:
        providers = load_required_mapping_section(config_path, "providers")
    except Exception as exc:
        raise ConfigError(str(exc)) from exc

    configs: Dict[str, ProviderToolConfig] = {}
    for provider_key, provider_payload in providers.items():
        if not isinstance(provider_payload, dict):
            raise ConfigError(f"Provider entry must be a mapping: {provider_key}")
        configs[str(provider_key)] = ProviderToolConfig.model_validate(provider_payload)
    return configs


def is_env_var_reference(value: Optional[str]) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    return candidate.replace("_", "").isalnum() and candidate.upper() == candidate and "-" not in candidate


def resolve_provider_api_key(config: ProviderToolConfig) -> str:
    env_name = str(config.api_key_env or "").strip()
    env_value = os.getenv(env_name) if env_name else None
    if env_value:
        return env_value
    if env_name and not is_env_var_reference(env_name):
        return env_name
    raise ConfigError(
        f"Missing API key for tool provider {config.provider_name}: {config.api_key_env}"
    )


def build_default_provider_tools(
    config_path: Union[str, Path] = DEFAULT_PROVIDER_CONFIG_PATH,
) -> Dict[str, Union[BaseProviderTool, OpenAICompatibleGatewayTool]]:
    configs = load_provider_tool_configs(config_path)
    return {
        "openai_compat": OpenAICompatibleGatewayTool(configs["openai_compat"]),
        "openai": OpenAITool(configs["openai"]),
        "chatgpt": ChatGPTTool(configs["chatgpt"]),
        "gemini": GeminiTool(configs["gemini"]),
        "claude": ClaudeTool(configs["claude"]),
    }

def get_default_provider_key(
    config_path: Union[str, Path] = DEFAULT_PROVIDER_CONFIG_PATH,
) -> str:
    """
    Resolve the default provider key using the following precedence:
    1. ZENTEX_DEFAULT_PROVIDER environment variable
    2. 'default_provider' key in config/provider_tools.yml
    3. 'openai' if OPENAI_API_KEY is present in env, else 'openai_compat'
    """
    env_default = os.getenv("ZENTEX_DEFAULT_PROVIDER")
    if env_default and env_default.strip():
        return env_default.strip()

    try:
        from zentex.core.config import load_yaml_config
        payload = load_yaml_config(config_path)
        config_default = payload.get("default_provider")
        if config_default and isinstance(config_default, str) and config_default.strip():
            return config_default.strip()
    except Exception:
        pass

    return "openai" if os.getenv("OPENAI_API_KEY") else "openai_compat"

