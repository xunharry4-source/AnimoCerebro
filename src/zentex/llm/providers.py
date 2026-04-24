from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.specs.model_provider import (
    ModelProviderAuthError as AuthError,
    ModelProviderConfigError as ConfigError,
    ModelProviderError,
    ModelProviderParseError as ResponseParseError,
    ModelProviderRateLimitError as RateLimitError,
    ModelProviderRemoteError as RemoteServiceError,
    ModelProviderTimeoutError as RemoteTimeoutError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROVIDER_CONFIG_PATH = PROJECT_ROOT / "config" / "provider_tools.yml"
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"


class ProviderToolConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider_name: str
    api_base: str
    api_key_env: str | None = None
    default_model: str = "default-model"
    timeout_seconds: float = 30.0


class ToolInvocationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    prompt: str
    system_prompt: str | None = None
    temperature: float = 0.2
    max_output_tokens: int = 1024
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolInvocationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    output_text: str
    usage: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Any] = Field(default_factory=dict)


def is_env_var_reference(value: str | None) -> bool:
    return bool(value and value.startswith("${") and value.endswith("}"))


def is_placeholder_secret(value: str | None) -> bool:
    if value is None:
        return False
    lowered = value.strip().lower()
    return lowered.startswith("your-") or lowered in {"changeme", "placeholder", "none"}


def load_project_dotenv(dotenv_path: Path | None = None) -> dict[str, str]:
    path = dotenv_path or DEFAULT_DOTENV_PATH
    if not path.exists():
        return {}
    env_map: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_map[key.strip()] = value.strip().strip("'\"")
    return env_map


def resolve_env_value(value: str | None) -> str | None:
    if value is None:
        return None
    if is_env_var_reference(value):
        return os.environ.get(value[2:-1])
    return os.environ.get(value, value)


def resolve_provider_api_key(config: ProviderToolConfig) -> str | None:
    return resolve_env_value(config.api_key_env)


def load_provider_tool_configs(config_path: Path | None = None) -> dict[str, ProviderToolConfig]:
    path = config_path or DEFAULT_PROVIDER_CONFIG_PATH
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    providers = payload.get("providers") or {}
    return {
        str(key): ProviderToolConfig.model_validate(value)
        for key, value in providers.items()
        if isinstance(value, dict)
    }


def get_default_provider_key(config_path: Path | None = None) -> str:
    payload = yaml.safe_load((config_path or DEFAULT_PROVIDER_CONFIG_PATH).read_text(encoding="utf-8")) or {}
    return str(payload.get("default_provider") or "openai").strip()


class BaseProviderTool(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    provider_key: str
    config: ProviderToolConfig

    def call(self, invocation: ToolInvocationRequest) -> ToolInvocationResponse:
        if self.config.api_key_env and not resolve_provider_api_key(self.config) and not self._is_local_provider():
            raise AuthError(f"Missing API key for provider {self.provider_key}")
        return ToolInvocationResponse(
            output_text="{}",
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            raw_response={
                "provider_key": self.provider_key,
                "model": invocation.model,
                "stub": True,
            },
        )

    def check_health(self) -> Any:
        class _Health:
            ok = True
            message = "stubbed"

            class status:
                value = "online"

        return _Health()

    def _is_local_provider(self) -> bool:
        return self.provider_key in {"ollama", "openai_compat"}


class OpenAITool(BaseProviderTool):
    pass


class ChatGPTTool(BaseProviderTool):
    pass


class OpenAICompatibleGatewayTool(BaseProviderTool):
    pass


class GeminiTool(BaseProviderTool):
    pass


class ClaudeTool(BaseProviderTool):
    pass


class OllamaTool(BaseProviderTool):
    pass


def resolve_ollama_model(model: str | None) -> str:
    return str(model or "gemma4:latest")


def build_default_provider_tools(config_path: Path | None = None) -> dict[str, BaseProviderTool]:
    tools: dict[str, BaseProviderTool] = {}
    tool_types = {
        "openai": OpenAITool,
        "chatgpt": ChatGPTTool,
        "openai_compat": OpenAICompatibleGatewayTool,
        "gemini": GeminiTool,
        "claude": ClaudeTool,
        "ollama": OllamaTool,
    }
    for provider_key, config in load_provider_tool_configs(config_path).items():
        tool_cls = tool_types.get(provider_key, BaseProviderTool)
        tools[provider_key] = tool_cls(provider_key=provider_key, config=config)
    return tools
