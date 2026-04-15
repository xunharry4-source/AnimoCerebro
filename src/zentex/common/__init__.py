"""Shared common abstractions for Zentex.

This package provides shared utilities and infrastructure:
- Database connection management (db_connection)
- Data Access Objects (database, dao_registry)
- Plugin registry (plugin_registry)
- State management (state)
- Coordination utilities (coordination)
- Locking mechanisms (locking)
- Protocol definitions (protocol)
- Plugin ID constants (plugin_ids)
"""

# Note: We use lazy imports to avoid circular dependencies and heavy imports at module load time
# Users should import specific modules directly when needed:
#   from zentex.common.db_connection import get_db_connection
#   from zentex.common.dao_registry import get_dao_registry
#   from zentex.common.database import BaseDAO, LRUCache
#   from zentex.common.plugin_ids import NINE_QUESTION_Q1, COGNITIVE_BUDGET_CONFLICT

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
    # Plugin ID constants
    'NINE_QUESTION_Q1',
    'NINE_QUESTION_Q2',
    'NINE_QUESTION_Q3',
    'NINE_QUESTION_Q4',
    'NINE_QUESTION_Q5',
    'NINE_QUESTION_Q6',
    'NINE_QUESTION_Q7',
    'NINE_QUESTION_Q8',
    'NINE_QUESTION_Q9',
    'COGNITIVE_BUDGET_CONFLICT',
    'COGNITIVE_EXPIRED_ASSUMPTION',
    'COGNITIVE_FAILURE_CLUSTER',
    'COGNITIVE_SEMANTIC_CONFLICT',
    'MEMORY_EXTRACTOR',
    'ORACLE_ALTERNATIVE',
    'ORACLE_OBJECTIVE',
    'ORACLE_POSTURE',
    'ORACLE_REDLINE',
    'REFLECTION_GENERATOR',
    'get_plugin_category',
    'is_cognitive_plugin',
    'is_nine_question_plugin',
    'get_nine_question_number',
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
    # Plugin ID constants - lazy load from plugin_ids module
    elif name in (
        'NINE_QUESTION_Q1', 'NINE_QUESTION_Q2', 'NINE_QUESTION_Q3',
        'NINE_QUESTION_Q4', 'NINE_QUESTION_Q5', 'NINE_QUESTION_Q6',
        'NINE_QUESTION_Q7', 'NINE_QUESTION_Q8', 'NINE_QUESTION_Q9',
        'COGNITIVE_BUDGET_CONFLICT', 'COGNITIVE_EXPIRED_ASSUMPTION',
        'COGNITIVE_FAILURE_CLUSTER', 'COGNITIVE_SEMANTIC_CONFLICT',
        'MEMORY_EXTRACTOR',
        'ORACLE_ALTERNATIVE', 'ORACLE_OBJECTIVE', 'ORACLE_POSTURE', 'ORACLE_REDLINE',
        'REFLECTION_GENERATOR',
        'get_plugin_category', 'is_cognitive_plugin',
        'is_nine_question_plugin', 'get_nine_question_number',
    ):
        from zentex.common import plugin_ids
        return getattr(plugin_ids, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
