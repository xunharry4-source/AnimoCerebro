"""
Canonical public entrypoint for plugin access in Zentex.

External callers must import plugin governance APIs from this module:
    from zentex.plugins.service import SystemPluginService

The modular implementation under ``src/zentex/plugins/service/`` is internal.
Callers must not import submodules such as ``service.manager`` directly.
"""

from __future__ import annotations

from typing import Any

from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.service.manager import SystemPluginService, PluginGovernanceService
from zentex.plugins.weights import WeightPluginAssembler, RationalAuditRejectError
from zentex.plugins.provider_tools import (
    AuthError,
    BaseProviderTool,
    ConfigError,
    OpenAICompatibleGatewayTool,
    RateLimitError,
    RemoteServiceError,
    RemoteTimeoutError,
    ResponseParseError,
    ToolInvocationRequest,
    ToolInvocationResponse,
    build_default_provider_tools,
    is_env_var_reference,
)


def get_default_provider_key() -> str:
    """
    Get the default LLM provider key from environment or config.
    
    This is the ONLY way external modules should access provider configuration.
    Never import zentex.plugins.provider_tools directly.
    
    Returns:
        Provider key string (e.g., 'openai', 'anthropic', etc.)
        
    Example:
        from zentex.plugins.service import get_default_provider_key
        provider = get_default_provider_key()
    """
    from zentex.plugins.provider_tools import get_default_provider_key as _get_key
    return _get_key()


def get_active_functional_plugins(plugin_service: SystemPluginService) -> list[dict[str, Any]]:
    """Return active functional plugin records from the public plugin service."""
    return plugin_service.query_by_category("functional", PluginLifecycleStatus.ACTIVE.value)


def get_active_cognitive_plugins(plugin_service: SystemPluginService) -> list[dict[str, Any]]:
    """Return active cognitive plugin records from the public plugin service."""
    return plugin_service.query_by_category("cognitive", PluginLifecycleStatus.ACTIVE.value)


__all__ = [
    "SystemPluginService",
    "PluginGovernanceService",
    "WeightPluginAssembler",
    "RationalAuditRejectError",
    "AuthError",
    "BaseProviderTool",
    "ConfigError",
    "OpenAICompatibleGatewayTool",
    "RateLimitError",
    "RemoteServiceError",
    "RemoteTimeoutError",
    "ResponseParseError",
    "ToolInvocationRequest",
    "ToolInvocationResponse",
    "build_default_provider_tools",
    "is_env_var_reference",
    "get_default_provider_key",
    "get_active_functional_plugins",
    "get_active_cognitive_plugins",
]
