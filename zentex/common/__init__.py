"""Shared common abstractions for Zentex.

This package provides shared utilities and infrastructure:
- Database connection management (db_connection)
- Data Access Objects (database, dao_registry)
- Plugin registry (plugin_registry)
- State management (state)
- Coordination utilities (coordination)
- Locking mechanisms (locking)
- Protocol definitions (protocol)
"""

# Note: We use lazy imports to avoid circular dependencies and heavy imports at module load time
# Users should import specific modules directly when needed:
#   from zentex.common.db_connection import get_db_connection
#   from zentex.common.dao_registry import get_dao_registry
#   from zentex.common.database import BaseDAO, LRUCache

__all__ = [
    # These are available but prefer direct imports for clarity
    'get_db_connection',
    'get_db_dependency', 
    'UnifiedDatabaseConnection',
    'get_dao_registry',
    'reset_dao_registry',
    'DAORegistry',
    'BaseDAO',
    'LRUCache',
    'DatabaseConnection',
]


def __getattr__(name):
    """Lazy attribute access to avoid heavy imports."""
    if name == 'get_db_connection':
        from zentex.common.db_connection import get_db_connection as func
        return func
    elif name == 'get_db_dependency':
        from zentex.common.db_connection import get_db_dependency as func
        return func
    elif name == 'UnifiedDatabaseConnection':
        from zentex.common.db_connection import UnifiedDatabaseConnection as cls
        return cls
    elif name == 'get_dao_registry':
        from zentex.common.dao_registry import get_dao_registry as func
        return func
    elif name == 'reset_dao_registry':
        from zentex.common.dao_registry import reset_dao_registry as func
        return func
    elif name == 'DAORegistry':
        from zentex.common.dao_registry import DAORegistry as cls
        return cls
    elif name == 'BaseDAO':
        from zentex.common.database import BaseDAO as cls
        return cls
    elif name == 'LRUCache':
        from zentex.common.database import LRUCache as cls
        return cls
    elif name == 'DatabaseConnection':
        from zentex.common.database import DatabaseConnection as cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
