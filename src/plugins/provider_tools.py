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
from zentex.launcher.config import CONFIG_DIR, load_required_mapping_section, load_yaml_config

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

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised through runtime config checks
    genai = None


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
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"


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
    def call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        if genai is None:
            raise ConfigError("google-genai package is not installed in the local environment")

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

    def _classify_sdk_error(self, exc: Exception) -> ModelProviderError:
        status_code = getattr(exc, "status_code", None)
        if status_code in {401, 403}:
            return AuthError(
                f"Authentication failed for provider {self.config.provider_name} with status {status_code}"
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
            return AuthError(f"Authentication failed for provider {self.config.provider_name}")
        if "rate" in message or "quota" in message or "429" in message:
            return RateLimitError(f"Rate limit exceeded for provider {self.config.provider_name}")
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return RemoteTimeoutError(
                f"Remote provider timeout or network failure for {self.config.provider_name}"
            )
        return RemoteTimeoutError(
            f"Remote provider timeout or network failure for {self.config.provider_name}"
        )

    def _response_to_dict(self, response: Any) -> Dict[str, Any]:
        if hasattr(response, "model_dump") and callable(response.model_dump):
            dumped = response.model_dump()
            return dumped if isinstance(dumped, dict) else {"response": dumped}
        if hasattr(response, "to_dict") and callable(response.to_dict):
            dumped = response.to_dict()
            return dumped if isinstance(dumped, dict) else {"response": dumped}
        text = getattr(response, "text", None)
        usage = getattr(response, "usage_metadata", None)
        usage_dict = None
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

    def _build_url(self) -> str:
        raise NotImplementedError("GeminiTool uses the official google.genai SDK")

    def _provider_headers(self, api_key: str) -> Dict[str, str]:
        raise NotImplementedError("GeminiTool uses the official google.genai SDK")

    def _build_payload(self, invocation: ToolInvocationRequest) -> Dict[str, Any]:
        raise NotImplementedError("GeminiTool uses the official google.genai SDK")

    def _extract_text(self, payload: Dict[str, Any]) -> str:
        return str(payload.get("text", "") or "")

    def _extract_usage(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        usage = payload.get("usage_metadata") or payload.get("usageMetadata")
        if not isinstance(usage, dict):
            return None
        return {
            "input_tokens": usage.get("prompt_token_count") or usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidates_token_count") or usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("total_token_count") or usage.get("totalTokenCount"),
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


def is_placeholder_secret(value: Optional[str]) -> bool:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return True
    known_placeholders = {
        "your-openai-key-here",
        "your-claude-key-here",
        "replace-me",
        "changeme",
    }
    return candidate in known_placeholders


@functools.lru_cache(maxsize=1)
def load_project_dotenv(
    dotenv_path: Union[str, os.PathLike[str], None] = None,
) -> Dict[str, str]:
    path = Path(dotenv_path) if dotenv_path is not None else DEFAULT_DOTENV_PATH
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_env_value(name: str) -> Optional[str]:
    key = str(name or "").strip()
    if not key:
        return None
    value = os.getenv(key)
    if value and not is_placeholder_secret(value):
        return value

    dotenv_values = load_project_dotenv()
    if key in dotenv_values and dotenv_values[key] and not is_placeholder_secret(dotenv_values[key]):
        return dotenv_values[key]

    # Gemini setups often use GOOGLE_API_KEY in .env while provider config names GEMINI_API_KEY.
    aliases: Dict[str, tuple[str, ...]] = {
        "GEMINI_API_KEY": ("GOOGLE_API_KEY",),
    }
    for alias in aliases.get(key, ()):
        alias_value = os.getenv(alias) or dotenv_values.get(alias)
        if alias_value and not is_placeholder_secret(alias_value):
            return alias_value
    return None


def resolve_provider_api_key(config: ProviderToolConfig) -> str:
    env_name = str(config.api_key_env or "").strip()
    env_value = resolve_env_value(env_name) if env_name else None
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
    env_default = resolve_env_value("ZENTEX_DEFAULT_PROVIDER")
    if env_default and env_default.strip():
        return env_default.strip()

    try:
        from zentex.launcher.config import load_yaml_config
        payload = load_yaml_config(config_path)
        config_default = payload.get("default_provider")
        if config_default and isinstance(config_default, str) and config_default.strip():
            return config_default.strip()
    except Exception:
        pass

    return "openai" if resolve_env_value("OPENAI_API_KEY") else "openai_compat"
