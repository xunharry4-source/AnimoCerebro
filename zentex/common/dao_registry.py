"""
DAO Registry - Centralized management of all Data Access Objects.

This module provides a unified interface for accessing all DAO instances,
ensuring consistent database connection and cache usage across the application.

Responsibilities:
- Initialize and manage database connection via UnifiedDatabaseConnection
- Create and cache DAO instances
- Provide dependency injection interface
- Ensure single connection per application lifecycle

Architecture:
- Singleton pattern for DAO registry
- Uses UnifiedDatabaseConnection for database access
- Lazy initialization of DAOs
- Shared LRUCache instance

Usage:
    # Get DAO registry (singleton)
    registry = get_dao_registry()
    
    # Initialize with database path (uses UnifiedDatabaseConnection internally)
    registry.initialize("runtime/data/zentex_core.db")
    
    # Get specific DAO
    agent_dao = registry.get_agent_dao()
    mcp_dao = registry.get_mcp_server_dao()
"""

from __future__ import annotations

import logging
from typing import Optional

from zentex.common.db_connection import get_db_connection, UnifiedDatabaseConnection
from zentex.common.database import LRUCache
from zentex.agents.dao import AgentDAO
from zentex.mcp.dao import McpServerDAO, McpToolDAO, McpExecutionRecordDAO
from zentex.cli.dao import CliToolDAO, CliExecutionHistoryDAO, CliCreditScoreDAO

logger = logging.getLogger(__name__)


class DAORegistry:
    """
    Central registry for all Data Access Objects.
    
    Ensures single database connection and shared cache across all DAOs.
    Implements singleton pattern to prevent multiple connections.
    Uses UnifiedDatabaseConnection for database access.
    """
    
    _instance: Optional['DAORegistry'] = None
    
    def __init__(self):
        """Initialize DAO registry (private - use get_dao_registry())."""
        if DAORegistry._instance is not None:
            raise RuntimeError("Use get_dao_registry() instead of creating new instance")
        
        self._db_conn: Optional[UnifiedDatabaseConnection] = None
        self._cache: Optional[LRUCache] = None
        self._initialized = False
        
        # DAO instances (lazy initialized)
        self._agent_dao: Optional[AgentDAO] = None
        self._mcp_server_dao: Optional[McpServerDAO] = None
        self._mcp_tool_dao: Optional[McpToolDAO] = None
        self._mcp_execution_dao: Optional[McpExecutionRecordDAO] = None
        self._cli_tool_dao: Optional[CliToolDAO] = None
        self._cli_execution_dao: Optional[CliExecutionHistoryDAO] = None
        self._cli_credit_dao: Optional[CliCreditScoreDAO] = None
    
    def initialize(self, db_path: str, cache_max_size: int = 1000, cache_ttl: int = 300):
        """
        Initialize the registry with database connection and cache.
        
        This method initializes the UnifiedDatabaseConnection and creates
        a shared LRUCache instance for all DAOs.
        
        Args:
            db_path: Path to SQLite database file
            cache_max_size: Maximum cache entries
            cache_ttl: Cache TTL in seconds
        """
        if self._initialized:
            logger.warning("DAORegistry already initialized, skipping")
            return
        
        logger.info(f"Initializing DAORegistry with database: {db_path}")
        
        # Initialize unified database connection
        self._db_conn = get_db_connection()
        self._db_conn.initialize(db_path, enable_wal=True)
        
        # Create shared cache
        self._cache = LRUCache(max_size=cache_max_size, ttl_seconds=cache_ttl)
        
        self._initialized = True
        logger.info("DAORegistry initialized successfully with UnifiedDatabaseConnection")
    
    @property
    def db(self) -> UnifiedDatabaseConnection:
        """Get unified database connection (must be initialized first)."""
        if not self._initialized or self._db_conn is None:
            raise RuntimeError("DAORegistry not initialized. Call initialize() first.")
        return self._db_conn
    
    @property
    def cache(self) -> LRUCache:
        """Get shared cache (must be initialized first)."""
        if not self._initialized or self._cache is None:
            raise RuntimeError("DAORegistry not initialized. Call initialize() first.")
        return self._cache
    
    def get_agent_dao(self) -> AgentDAO:
        """Get or create AgentDAO instance."""
        if self._agent_dao is None:
            self._agent_dao = AgentDAO(self.db, self.cache)
        return self._agent_dao
    
    def get_mcp_server_dao(self) -> McpServerDAO:
        """Get or create McpServerDAO instance."""
        if self._mcp_server_dao is None:
            self._mcp_server_dao = McpServerDAO(self.db, self.cache)
        return self._mcp_server_dao
    
    def get_mcp_tool_dao(self) -> McpToolDAO:
        """Get or create McpToolDAO instance."""
        if self._mcp_tool_dao is None:
            self._mcp_tool_dao = McpToolDAO(self.db, self.cache)
        return self._mcp_tool_dao
    
    def get_mcp_execution_dao(self) -> McpExecutionRecordDAO:
        """Get or create McpExecutionRecordDAO instance."""
        if self._mcp_execution_dao is None:
            self._mcp_execution_dao = McpExecutionRecordDAO(self.db, self.cache)
        return self._mcp_execution_dao
    
    def get_cli_tool_dao(self) -> CliToolDAO:
        """Get or create CliToolDAO instance."""
        if self._cli_tool_dao is None:
            self._cli_tool_dao = CliToolDAO(self.db, self.cache)
        return self._cli_tool_dao
    
    def get_cli_execution_dao(self) -> CliExecutionHistoryDAO:
        """Get or create CliExecutionHistoryDAO instance."""
        if self._cli_execution_dao is None:
            self._cli_execution_dao = CliExecutionHistoryDAO(self.db, self.cache)
        return self._cli_execution_dao
    
    def get_cli_credit_dao(self) -> CliCreditScoreDAO:
        """Get or create CliCreditScoreDAO instance."""
        if self._cli_credit_dao is None:
            self._cli_credit_dao = CliCreditScoreDAO(self.db, self.cache)
        return self._cli_credit_dao
    
    def clear_all_caches(self):
        """Clear all cached data (useful for testing or admin operations)."""
        if self._cache:
            self._cache.clear()
            logger.info("All DAO caches cleared")
    
    def shutdown(self):
        """
        Shutdown the registry and clean up resources.
        
        Closes the unified database connection and clears all caches.
        """
        logger.info("Shutting down DAORegistry")
        
        # Shutdown unified database connection
        if self._db_conn:
            try:
                self._db_conn.shutdown()
                logger.info("UnifiedDatabaseConnection shutdown")
            except Exception as e:
                logger.error(f"Error shutting down database connection: {e}")
        
        # Clear cache
        if self._cache:
            self._cache.clear()
        
        # Reset state
        self._initialized = False
        self._db_conn = None
        self._cache = None
        self._agent_dao = None
        self._mcp_server_dao = None
        self._mcp_tool_dao = None
        self._mcp_execution_dao = None
        self._cli_tool_dao = None
        self._cli_execution_dao = None
        self._cli_credit_dao = None


def get_dao_registry() -> DAORegistry:
    """
    Get the singleton DAORegistry instance.
    
    Returns:
        DAORegistry singleton instance
    """
    if DAORegistry._instance is None:
        DAORegistry._instance = DAORegistry()
    return DAORegistry._instance


def reset_dao_registry():
    """Reset the singleton instance (primarily for testing)."""
    if DAORegistry._instance is not None:
        DAORegistry._instance.shutdown()
        DAORegistry._instance = None
