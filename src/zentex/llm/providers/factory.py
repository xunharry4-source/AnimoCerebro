"""
Factory: builds the full set of provider tool instances from config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Union

from .base import BaseProviderTool, DEFAULT_PROVIDER_CONFIG_PATH
from .config import load_provider_tool_configs
from .openai import ChatGPTTool, OpenAICompatibleGatewayTool, OpenAITool
from .gemini import GeminiTool
from .claude import ClaudeTool
from .ollama import OllamaTool


def build_default_provider_tools(
    config_path: Union[str, Path] = DEFAULT_PROVIDER_CONFIG_PATH,
    *,
    refresh: bool = False,
) -> Dict[str, Union[BaseProviderTool, OpenAICompatibleGatewayTool]]:
    """Instantiate all configured provider tools and return them keyed by provider name.

    Pass ``refresh=True`` to clear the config LRU cache before loading,
    which forces re-reading from disk (useful after YAML edits).
    """
    if refresh:
        load_provider_tool_configs.cache_clear()
    configs = load_provider_tool_configs(config_path)
    return {
        "openai_compat": OpenAICompatibleGatewayTool(configs["openai_compat"]),
        "openai":        OpenAITool(configs["openai"]),
        "chatgpt":       ChatGPTTool(configs["chatgpt"]),
        "gemini":        GeminiTool(configs["gemini"]),
        "claude":        ClaudeTool(configs["claude"]),
        "ollama":        OllamaTool(configs["ollama"]),
    }
