from __future__ import annotations
"""
Database access layer for Zentex persistent storage.

This module provides a unified database interface with connection pooling,
automatic schema migration, and query caching support.

Responsibilities:
- Manage SQLite database connections with WAL mode for concurrent reads
- Provide base DAO class with common CRUD operations
- Implement thread-safe LRU cache for frequently accessed data
- Ensure all database operations are logged with trace_id

Architecture:
- DatabaseConnection: Thread-safe connection manager
- LRUCache: In-memory cache with TTL to reduce DB queries
- BaseDAO: Common data access patterns inherited by specific DAOs

Usage:
    db = DatabaseConnection(get_storage_paths().core_db)
    dao = AgentDAO(db)
    agent = dao.find_by_id("agent-123")
"""


import json
import logging
import sqlite3
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class DatabaseConnection:
    """
    Thread-safe SQLite database connection manager with WAL mode.
    
    Features:
    - Thread-local connections to avoid contention
    - WAL (Write-Ahead Logging) mode for better concurrent read performance
    - Foreign key enforcement
    - Automatic transaction management
    
    Usage:
        db = DatabaseConnection("path/to/db.sqlite")
        with db.get_connection() as conn:
            conn.execute("SELECT * FROM agents")
    """
    
    def __init__(self, db_path: str, enable_wal: bool = True):
        """
        Initialize database connection manager.
        
        Args:
            db_path: Path to SQLite database file
            enable_wal: Enable WAL mode for better concurrent read performance
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = Lock()
        
        if enable_wal:
            self._enable_wal_mode()
        
        logger.info(f"DatabaseConnection initialized: {self.db_path}")
    
    def _enable_wal_mode(self):
        """Enable WAL mode for better concurrent read performance."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            logger.info(f"WAL mode enabled for {self.db_path}")
        finally:
            conn.close()
    
    @contextmanager
    def get_connection(self):
        """
        Get a thread-local database connection with automatic transaction management.
        
        Yields:
            sqlite3.Connection: Thread-local database connection
            
        Example:
            with db.get_connection() as conn:
                conn.execute("INSERT INTO agents ...")
                # Auto-committed on success, auto-rolled back on exception
        """
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        
        conn = self._local.connection
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
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return row[0] if row else None


# Import threading here to avoid circular dependency issues
import threading


class LRUCache(Generic[T]):
    """
    Thread-safe LRU cache with TTL support.
    
    Features:
    - Configurable max size
    - Time-to-live (TTL) for cache entries
    - Thread-safe operations
    - Pattern-based invalidation
    
    Usage:
        cache = LRUCache(max_size=1000, ttl_seconds=300)
        cache.set("key", value)
        value = cache.get("key")  # Returns None if expired or not found
        cache.invalidate_pattern("agents:")  # Invalidate all agent cache entries
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of entries in cache
            ttl_seconds: Time-to-live in seconds for cache entries
        """
        self._cache: OrderedDict[str, tuple[T, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[T]:
        """
        Get value from cache if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found or expired
        """
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if (datetime.now(timezone.utc).timestamp() - timestamp) < self._ttl_seconds:
                    # Move to end (most recently used)
                    self._cache.move_to_end(key)
                    return value
                else:
                    # Expired
                    del self._cache[key]
            return None
    
    def set(self, key: str, value: T):
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, datetime.now(timezone.utc).timestamp())
            
            # Evict oldest if over capacity
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
    
    def invalidate(self, key: str):
        """
        Remove specific key from cache.
        
        Args:
            key: Cache key to remove
        """
        with self._lock:
            self._cache.pop(key, None)
    
    def invalidate_pattern(self, pattern: str):
        """
        Remove keys matching pattern (simple prefix match).
        
        Args:
            pattern: Prefix pattern to match cache keys
        """
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_remove:
                del self._cache[key]
    
    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)


class BaseDAO:
    """
    Base Data Access Object with common CRUD operations and caching.
    
    Features:
    - Automatic cache management
    - JSON serialization/deserialization helpers
    - Timestamp management
    - Pattern-based cache invalidation
    
    Subclasses should:
    - Set self.table_name in __init__
    - Override entity-specific methods as needed
    
    Usage:
        class AgentDAO(BaseDAO):
            def __init__(self, db: DatabaseConnection, cache: LRUCache = None):
                super().__init__(db, cache)
                self.table_name = "agents"
    """
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        """
        Initialize BaseDAO.
        
        Args:
            db: DatabaseConnection instance
            cache: Optional LRUCache instance (creates default if None)
        """
        self.db = db
        self.cache = cache or LRUCache()
        self.table_name: str = ""  # Must be set by subclasses

    def _get_table_columns(self) -> set[str]:
        """Return the current table's column names."""
        rows = self.db.execute_query(f"PRAGMA table_info({self.table_name})")
        return {str(row["name"]) for row in rows}

    def _default_order_by(self) -> str:
        """Choose a stable default ordering based on available columns."""
        columns = self._get_table_columns()
        if "updated_at" in columns:
            return "updated_at DESC"
        if "last_updated_at" in columns:
            return "last_updated_at DESC"
        if "created_at" in columns:
            return "created_at DESC"
        if "timestamp" in columns:
            return "timestamp DESC"
        if "recorded_at" in columns:
            return "recorded_at DESC"
        return f"{self._get_id_column()} DESC"
    
    def _cache_key(self, operation: str, **kwargs) -> str:
        """
        Generate cache key from operation and parameters.
        
        Args:
            operation: Operation name (e.g., "find_by_id")
            **kwargs: Additional parameters
            
        Returns:
            Cache key string
        """
        key_parts = [self.table_name, operation]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        return ":".join(key_parts)
    
    def _invalidate_cache(self, pattern: str):
        """
        Invalidate cache entries matching pattern.
        
        Args:
            pattern: Cache key prefix pattern
        """
        if self.cache:
            self.cache.invalidate_pattern(pattern)
            logger.debug(f"Cache invalidated for pattern: {pattern}")
    
    def _serialize_json(self, obj: Any) -> Optional[str]:
        """Serialize object to JSON string."""
        if obj is None:
            return None
        return json.dumps(obj, ensure_ascii=False, default=str)
    
    def _deserialize_json(self, json_str: Optional[str]) -> Any:
        """Deserialize JSON string to object."""
        if json_str is None:
            return None
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to deserialize JSON: {json_str}")
            return None
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert sqlite3.Row to dictionary with JSON deserialization."""
        result = dict(row)
        # Deserialize JSON fields
        for key, value in result.items():
            if isinstance(value, str) and (
                key in ('scope', 'capabilities', 'metadata', 'args', 'env', 
                       'input_schema', 'parameters', 'details', 'command_line')
            ):
                result[key] = self._deserialize_json(value)
        return result
    
    def find_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Find entity by ID.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            Entity dictionary or None if not found
        """
        cache_key = self._cache_key("find_by_id", id=entity_id)
        
        # Try cache first
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached
        
        # Query database
        query = f"SELECT * FROM {self.table_name} WHERE {self._get_id_column()} = ?"
        rows = self.db.execute_query(query, (entity_id,))
        
        if not rows:
            return None
        
        result = self._row_to_dict(rows[0])
        
        # Cache result
        self.cache.set(cache_key, result)
        logger.debug(f"Cache set for {cache_key}")
        
        return result
    
    def find_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Find all entities with pagination.
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of entity dictionaries
        """
        cache_key = self._cache_key("find_all", limit=limit, offset=offset)
        
        # Try cache first
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached
        
        # Query database
        query = f"SELECT * FROM {self.table_name} ORDER BY {self._default_order_by()} LIMIT ? OFFSET ?"
        rows = self.db.execute_query(query, (limit, offset))
        
        results = [self._row_to_dict(row) for row in rows]
        
        # Cache result
        self.cache.set(cache_key, results)
        logger.debug(f"Cache set for {cache_key}")
        
        return results
    
    def count(self) -> int:
        """
        Count total number of entities.
        
        Returns:
            Total count
        """
        cache_key = self._cache_key("count")
        
        # Try cache first
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Query database
        query = f"SELECT COUNT(*) FROM {self.table_name}"
        count = self.db.execute_scalar(query)
        
        # Cache result (shorter TTL for counts)
        self.cache.set(cache_key, count)
        
        return count
    
    def insert(self, data: Dict[str, Any]) -> bool:
        """
        Insert a new entity.
        
        Args:
            data: Entity data dictionary
            
        Returns:
            True if inserted successfully
        """
        # Serialize JSON fields
        processed_data = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                processed_data[key] = self._serialize_json(value)
            else:
                processed_data[key] = value
        
        columns = self._get_table_columns()

        # Add timestamps only when the table actually supports them.
        now = datetime.now(timezone.utc).isoformat()
        if 'created_at' in columns and 'created_at' not in processed_data:
            processed_data['created_at'] = now
        if 'updated_at' in columns and 'updated_at' not in processed_data:
            processed_data['updated_at'] = now
        
        columns = ', '.join(processed_data.keys())
        placeholders = ', '.join(['?' for _ in processed_data])
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        
        try:
            self.db.execute_update(query, tuple(processed_data.values()))
            # Invalidate cache
            self._invalidate_cache(f"{self.table_name}:")
            logger.info(f"Inserted into {self.table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to insert into {self.table_name}: {e}")
            return False
    
    def update(self, entity_id: str, data: Dict[str, Any]) -> bool:
        """
        Update an existing entity.
        
        Args:
            entity_id: Entity identifier
            data: Fields to update
            
        Returns:
            True if updated successfully
        """
        if not data:
            return False
        
        # Serialize JSON fields
        processed_data = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                processed_data[key] = self._serialize_json(value)
            else:
                processed_data[key] = value
        
        columns = self._get_table_columns()

        # Update timestamp only when supported by the table.
        if 'updated_at' in columns:
            processed_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Build UPDATE query
        set_clause = ', '.join([f"{key} = ?" for key in processed_data.keys()])
        id_column = self._get_id_column()
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {id_column} = ?"
        
        params = list(processed_data.values()) + [entity_id]
        
        try:
            affected = self.db.execute_update(query, tuple(params))
            if affected > 0:
                # Invalidate cache
                self._invalidate_cache(f"{self.table_name}:")
                logger.info(f"Updated {self.table_name} entity: {entity_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update {self.table_name} entity {entity_id}: {e}")
            return False
    
    def find_by_condition(
        self, 
        condition: str, 
        params: tuple = (),
        order_by: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find entities by custom condition.
        
        Args:
            condition: WHERE clause (without 'WHERE' keyword)
            params: Query parameters
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of entity dictionaries
        """
        query = (
            f"SELECT * FROM {self.table_name} WHERE {condition} "
            f"ORDER BY {order_by or self._default_order_by()} LIMIT ? OFFSET ?"
        )
        rows = self.db.execute_query(query, params + (limit, offset))
        return [self._row_to_dict(row) for row in rows]
    
    def delete(self, entity_id: str) -> bool:
        """
        Delete entity by ID.
        
        Args:
            entity_id: Entity identifier
            
        Returns:
            True if deleted, False if not found
        """
        query = f"DELETE FROM {self.table_name} WHERE {self._get_id_column()} = ?"
        affected = self.db.execute_update(query, (entity_id,))
        
        if affected > 0:
            # Invalidate related cache entries
            self._invalidate_cache(f"{self.table_name}:")
            logger.info(f"Deleted {self.table_name} entity: {entity_id}")
            return True
        
        return False
    
    def _get_id_column(self) -> str:
        """
        Get the primary key column name for this table.
        
        Override in subclasses if different from default.
        
        Returns:
            Primary key column name
        """
        # Default implementation - override in subclasses
        if self.table_name == "agents":
            return "agent_id"
        elif self.table_name == "mcp_servers":
            return "server_id"
        elif self.table_name == "cli_tools":
            return "command_name"
        else:
            return "id"
