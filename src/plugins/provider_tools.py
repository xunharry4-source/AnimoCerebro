"""
Backward-compatibility shim.

All provider implementations have moved to ``zentex.llm.providers.*``.
This module re-exports every public symbol so existing import paths
(``from plugins.provider_tools import ...``) continue to work unchanged.
"""
from zentex.llm.providers import (  # noqa: F401
    # base models & errors
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
    # config / env helpers
    is_env_var_reference,
    is_placeholder_secret,
    load_project_dotenv,
    resolve_env_value,
    resolve_provider_api_key,
    load_provider_tool_configs,
    get_default_provider_key,
    # providers
    OpenAITool,
    ChatGPTTool,
    OpenAICompatibleGatewayTool,
    GeminiTool,
    ClaudeTool,
    OllamaTool,
    resolve_ollama_model,
    # factory
    build_default_provider_tools,
)
