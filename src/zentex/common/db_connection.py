"""
Unified Database Connection Manager for Zentex.

This module provides a singleton database connection that is shared across
the entire application, ensuring consistent access to the persistent storage.

Responsibilities:
- Manage a single SQLite database connection with WAL mode
- Provide thread-safe access to the database
- Handle connection lifecycle (initialize, shutdown)
- Support dependency injection via FastAPI

Architecture:
- Singleton pattern ensures one connection per application
- WAL mode enabled for concurrent read performance
- Foreign keys enforced for data integrity
- Automatic transaction management

Usage:
    # Get the unified database connection
    from zentex.common.db_connection import get_db_connection
    
    db = get_db_connection()
    
    # Use in FastAPI dependency
    from fastapi import Depends
    
    def get_db():
        return get_db_connection()
    
    @router.get("/items")
    def list_items(db = Depends(get_db)):
        rows = db.execute_query("SELECT * FROM items")
        return rows
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class UnifiedDatabaseConnection:
    """
    Singleton database connection manager for Zentex application.
    
    Provides a unified interface to the SQLite database with:
    - Thread-safe connection management
    - WAL mode for concurrent reads
    - Foreign key enforcement
    - Automatic transaction handling
    
    This class implements the singleton pattern to ensure only one
    database connection exists per application lifecycle.
    """
    
    _instance: Optional['UnifiedDatabaseConnection'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'UnifiedDatabaseConnection':
        """Create or return the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the database connection (called once)."""
        # __init__ may be called multiple times, so check _initialized
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._local = threading.local()
        self._db_path: Optional[Path] = None
        self._initialized = False
        
        logger.info("UnifiedDatabaseConnection created (not yet initialized)")
    
    def initialize(self, db_path: str, enable_wal: bool = True) -> None:
        """
        Initialize the database connection with the specified path.
        
        Args:
            db_path: Path to the SQLite database file
            enable_wal: Enable WAL mode for better concurrent read performance
            
        Raises:
            RuntimeError: If already initialized
        """
        if self._initialized:
            logger.warning("Database connection already initialized, skipping")
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Test connection
            test_conn = sqlite3.connect(str(self._db_path))
            try:
                if enable_wal:
                    test_conn.execute("PRAGMA journal_mode=WAL")
                    test_conn.execute("PRAGMA synchronous=NORMAL")
                    test_conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
                    logger.info(f"WAL mode enabled for {self._db_path}")
                
                test_conn.execute("PRAGMA foreign_keys=ON")
                logger.info(f"Foreign keys enabled for {self._db_path}")
                
                # Verify database is accessible
                test_conn.execute("SELECT 1")
                
            finally:
                test_conn.close()
            
            self._initialized = True
            logger.info(f"UnifiedDatabaseConnection initialized: {self._db_path}")
    
    @property
    def is_initialized(self) -> bool:
        """Check if the connection has been initialized."""
        return self._initialized
    
    @property
    def db_path(self) -> Optional[Path]:
        """Get the database file path."""
        return self._db_path
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a thread-local database connection.
        
        Creates a new connection if one doesn't exist for the current thread.
        
        Returns:
            sqlite3.Connection: Thread-local database connection
        """
        if not self._initialized:
            raise RuntimeError(
                "Database connection not initialized. "
                "Call initialize() first or ensure app startup has run."
            )
        
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA foreign_keys=ON")
            logger.debug(f"Created new thread-local connection for thread {threading.current_thread().name}")
        
        return self._local.connection
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connection with automatic transaction management.
        
        Yields:
            sqlite3.Connection: Thread-local database connection
            
        Example:
            with db.get_connection() as conn:
                conn.execute("INSERT INTO agents ...")
                # Auto-committed on success, auto-rolled back on exception
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction failed: {e}", exc_info=True)
            raise
    
    def execute_query(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL SELECT query with optional placeholders
            params: Query parameters
            
        Returns:
            List of rows as sqlite3.Row objects
            
        Example:
            rows = db.execute_query("SELECT * FROM agents WHERE status = ?", ("ACTIVE",))
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    
    def execute_update(self, query: str, params: tuple = ()) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query and return affected rows.
        
        Args:
            query: SQL DML query with optional placeholders
            params: Query parameters
            
        Returns:
            Number of affected rows
            
        Example:
            affected = db.execute_update("UPDATE agents SET status = ? WHERE agent_id = ?", 
                                        ("ACTIVE", "agent-123"))
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.rowcount
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """
        Execute batch operations.
        
        Args:
            query: SQL query with placeholders
            params_list: List of parameter tuples
            
        Returns:
            Total number of affected rows
            
        Example:
            db.execute_many("INSERT INTO agents (...) VALUES (...)", [
                (data1,),
                (data2,),
            ])
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(query, params_list)
            return cursor.rowcount
    
    def execute_scalar(self, query: str, params: tuple = ()) -> Any:
        """
        Execute a query and return a single scalar value.
        
        Args:
            query: SQL query returning a single value
            params: Query parameters
            
        Returns:
            Single scalar value or None
            
        Example:
            count = db.execute_scalar("SELECT COUNT(*) FROM agents")
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return row[0] if row else None
    
    def execute_script(self, sql_script: str) -> None:
        """
        Execute multiple SQL statements as a script.
        
        Args:
            sql_script: SQL script containing multiple statements
            
        Example:
            db.execute_script(open('schema.sql').read())
        """
        with self.get_connection() as conn:
            conn.executescript(sql_script)
    
    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            True if table exists, False otherwise
        """
        result = self.execute_scalar(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return result > 0
    
    def get_table_names(self) -> List[str]:
        """
        Get all table names in the database.
        
        Returns:
            List of table names
        """
        rows = self.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row['name'] for row in rows]
    
    def shutdown(self) -> None:
        """
        Shutdown the database connection and clean up resources.
        
        Closes all thread-local connections and resets the singleton.
        """
        if not self._initialized:
            return
        
        with self._lock:
            if hasattr(self._local, 'connection'):
                try:
                    self._local.connection.close()
                    logger.info("Database connection closed")
                except Exception as e:
                    logger.error(f"Error closing database connection: {e}")
                finally:
                    del self._local.connection
            
            self._initialized = False
            self._db_path = None
            
            # Reset singleton
            UnifiedDatabaseConnection._instance = None
            logger.info("UnifiedDatabaseConnection shutdown complete")


# Module-level singleton accessor
def get_db_connection() -> UnifiedDatabaseConnection:
    """
    Get the unified database connection singleton.
    
    Returns:
        UnifiedDatabaseConnection: The singleton database connection
        
    Example:
        db = get_db_connection()
        db.initialize("runtime/data/zentex_core.db")
    """
    return UnifiedDatabaseConnection()


# FastAPI dependency function
def get_db_dependency():
    """
    FastAPI dependency for database connection.
    
    Usage:
        from fastapi import Depends
        
        @router.get("/agents")
        def list_agents(db = Depends(get_db_dependency)):
            return db.execute_query("SELECT * FROM agents")
    """
    db = get_db_connection()
    if not db.is_initialized:
        raise RuntimeError(
            "Database not initialized. Ensure app startup has called db.initialize()"
        )
    return db
