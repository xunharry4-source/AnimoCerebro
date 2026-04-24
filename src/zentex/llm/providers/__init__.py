"""
LLM provider adapters — one file per provider.

Import from this package directly, or use the backward-compat shim
``plugins.provider_tools`` which re-exports everything from here.
"""
from .base import (
    ProviderToolConfig,
    ToolInvocationRequest,
    ToolInvocationResponse,
    ModelProviderError,
    ConfigError,
    AuthError,
    RemoteTimeoutError,
    RemoteServiceError,
    RateLimitError,
    ResponseParseError,
    BaseProviderTool,
    DEFAULT_PROVIDER_CONFIG_PATH,
    DEFAULT_DOTENV_PATH,
    PROJECT_ROOT,
)
from .config import (
    is_env_var_reference,
    is_placeholder_secret,
    load_project_dotenv,
    resolve_env_value,
    resolve_provider_api_key,
    load_provider_tool_configs,
    get_default_provider_key,
)
from .openai import OpenAITool, ChatGPTTool, OpenAICompatibleGatewayTool
from .gemini import GeminiTool
from .claude import ClaudeTool
from .ollama import OllamaTool, resolve_ollama_model
from .factory import build_default_provider_tools

__all__ = [
    # base models & errors
    "ProviderToolConfig",
    "ToolInvocationRequest",
    "ToolInvocationResponse",
    "ModelProviderError",
    "ConfigError",
    "AuthError",
    "RemoteTimeoutError",
    "RemoteServiceError",
    "RateLimitError",
    "ResponseParseError",
    "BaseProviderTool",
    "DEFAULT_PROVIDER_CONFIG_PATH",
    "DEFAULT_DOTENV_PATH",
    "PROJECT_ROOT",
    # config / env
    "is_env_var_reference",
    "is_placeholder_secret",
    "load_project_dotenv",
    "resolve_env_value",
    "resolve_provider_api_key",
    "load_provider_tool_configs",
    "get_default_provider_key",
    # providers
    "OpenAITool",
    "ChatGPTTool",
    "OpenAICompatibleGatewayTool",
    "GeminiTool",
    "ClaudeTool",
    "OllamaTool",
    "resolve_ollama_model",
    # factory
    "build_default_provider_tools",
]
