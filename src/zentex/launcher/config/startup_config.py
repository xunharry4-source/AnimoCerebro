"""
Startup configuration dataclasses for zentex.launcher.

All config objects use stdlib dataclasses (not Pydantic) because fields are
mutated during the loading phase by EnvReader and other pre-validation steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DatabaseConfig:
    """Database / persistence configuration."""

    sqlite_dir: str = "app_data"
    transcript_dir: str = "app_data/transcripts"
    pool_size: int = 5
    timeout_seconds: int = 30


@dataclass
class LLMConfig:
    """Language-model provider configuration."""

    provider: str = "anthropic"
    # Name of the environment variable that holds the API key — not the value itself.
    api_key_env: str = "ANTHROPIC_API_KEY"
    default_model: str = "claude-sonnet-4-6"
    timeout_seconds: int = 60
    max_retries: int = 3


@dataclass
class KernelConfig:
    """Kernel runtime configuration."""

    session_timeout_seconds: int = 1800
    turn_max_concurrency: int = 10
    working_memory_slots: int = 16
    transcript_db_dir: str = "app_data/transcripts"


@dataclass
class WebConfig:
    """Web-server / API configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    websocket_timeout_seconds: int = 300
    debug: bool = False


@dataclass
class PluginConfig:
    """Plugin loading configuration."""

    plugin_dirs: list[str] = field(default_factory=list)
    enabled_plugins: list[str] = field(default_factory=list)
    disabled_plugins: list[str] = field(default_factory=list)


@dataclass
class StartupConfig:
    """Root configuration object assembled before system startup."""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    kernel: KernelConfig = field(default_factory=KernelConfig)
    web: WebConfig = field(default_factory=WebConfig)
    plugins: PluginConfig = field(default_factory=PluginConfig)
    # "development" or "production"
    environment: str = "development"
