"""Configuration Management Contract

Centralizes configuration access, replacing scattered runtime properties
like runtime.default_workspace.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .kernel_service import AppConfig


class ConfigManager(ABC):
    """Centralized application configuration access
    
    Replaces: runtime.default_workspace, scattered config properties
    """

    @abstractmethod
    def get_default_workspace(self) -> str:
        """Get default workspace path
        
        Returns:
            Workspace path (default: ".")
        """
        pass

    @abstractmethod
    def get_transcript_db_path(self) -> str:
        """Get transcript database path
        
        Returns:
            SQLite database file path
        """
        pass

    @abstractmethod
    def get_session_db_path(self) -> str:
        """Get session database path
        
        Returns:
            SQLite database file path
        """
        pass

    @abstractmethod
    def get_cache_ttl(self) -> int:
        """Get cache time-to-live in seconds
        
        Returns:
            TTL in seconds (default: 3600)
        """
        pass

    @abstractmethod
    def get_log_level(self) -> str:
        """Get logging level
        
        Returns:
            Log level (INFO, DEBUG, etc.)
        """
        pass

    @abstractmethod
    def get_config(self) -> AppConfig:
        """Get complete configuration object
        
        Returns:
            AppConfig with all settings
        """
        pass
