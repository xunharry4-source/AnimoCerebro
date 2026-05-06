from __future__ import annotations
"""
Plugin ID Constants for Cognitive Plugins

This module centralizes all cognitive plugin IDs to ensure consistency
across the codebase and avoid hard-coded string literals.

Usage:
    from zentex.common.plugin_ids import (
        NINE_QUESTION_Q1,
        NINE_QUESTION_Q2,
        COGNITIVE_BUDGET_CONFLICT,
        # ... other plugin IDs
    )
"""



# ============================================================================
# Nine Questions Plugin IDs (Q1-Q9)
# ============================================================================

NINE_QUESTION_Q1 = "nine-question-q1-where-am-i"
"""Q1: 我在那 - Workspace domain inference"""

NINE_QUESTION_Q2 = "nine-question-q2-asset-inventory"
"""Q2: 我有什么 - Asset inventory and resources"""

NINE_QUESTION_Q3 = "nine-question-q3-who-am-i"
"""Q3: 我是谁 - Role and mission-boundary inference"""

NINE_QUESTION_Q4 = "nine-question-q4-what-can-i-do"
"""Q4: 我能做什么 - Capability boundary assessment"""

NINE_QUESTION_Q5 = "nine-question-q5-what-am-i-allowed-to-do"
"""Q5: 我被允许做什么 - Authorization boundary"""

NINE_QUESTION_Q6 = "nine-question-q6-what-should-i-not-do"
"""Q6: 我不应该做什么 - Forbidden zone and redlines"""

NINE_QUESTION_Q7 = "nine_question_q7_alternatives"
"""Q7: 我还能做什么 - Alternative options exploration"""

NINE_QUESTION_Q8 = "nine_question_q8_decision"
"""Q8: 我现在应该做什么 - Decision making"""

NINE_QUESTION_Q9 = "nine_question_q9_posture"
"""Q9: 我应该如何行动 - Action posture and strategy"""

# List of all nine question plugin IDs
NINE_QUESTIONS_ALL = [
    NINE_QUESTION_Q1,
    NINE_QUESTION_Q2,
    NINE_QUESTION_Q3,
    NINE_QUESTION_Q4,
    NINE_QUESTION_Q5,
    NINE_QUESTION_Q6,
    NINE_QUESTION_Q7,
    NINE_QUESTION_Q8,
    NINE_QUESTION_Q9,
]


# ============================================================================
# Cognitive Analysis Plugin IDs
# ============================================================================

COGNITIVE_BUDGET_CONFLICT = "cognitive_budget_conflict"
"""Budget conflict detection and resolution"""

COGNITIVE_EXPIRED_ASSUMPTION = "cognitive_expired_assumption"
"""Expired assumption cleaner"""

COGNITIVE_FAILURE_CLUSTER = "cognitive_failure_cluster"
"""Failure mode clustering and analysis"""

COGNITIVE_SEMANTIC_CONFLICT = "cognitive_semantic_conflict"
"""Semantic conflict detection"""

# List of all cognitive analysis plugin IDs
COGNITIVE_ANALYSIS_PLUGINS = [
    COGNITIVE_BUDGET_CONFLICT,
    COGNITIVE_EXPIRED_ASSUMPTION,
    COGNITIVE_FAILURE_CLUSTER,
    COGNITIVE_SEMANTIC_CONFLICT,
]


# ============================================================================
# Memory Plugin IDs
# ============================================================================

MEMORY_EXTRACTOR = "memory_extractor"
"""Memory extraction and indexing plugin"""

MEMORY_PLUGINS = [
    MEMORY_EXTRACTOR,
]


# ============================================================================
# Oracle Plugin IDs
# ============================================================================

ORACLE_ALTERNATIVE = "oracle_alternative"
"""Alternative scenario oracle"""

ORACLE_OBJECTIVE = "oracle_objective"
"""Objective validation oracle"""

ORACLE_POSTURE = "oracle_posture"
"""Posture recommendation oracle"""

ORACLE_REDLINE = "oracle_redline"
"""Redline enforcement oracle"""

# List of all oracle plugin IDs
ORACLE_PLUGINS = [
    ORACLE_ALTERNATIVE,
    ORACLE_OBJECTIVE,
    ORACLE_POSTURE,
    ORACLE_REDLINE,
]


# ============================================================================
# Reflection Plugin IDs
# ============================================================================

REFLECTION_GENERATOR = "reflection_generator"
"""Reflection generation and analysis"""

REFLECTION_PLUGINS = [
    REFLECTION_GENERATOR,
]


# ============================================================================
# All Cognitive-Layer Plugin IDs
# ============================================================================

# Combined list of all cognitive-layer plugins (excludes functional plugins like oracles)
ALL_COGNITIVE_PLUGINS = (
    NINE_QUESTIONS_ALL
    + COGNITIVE_ANALYSIS_PLUGINS
    + MEMORY_PLUGINS
    + REFLECTION_PLUGINS
)


# ============================================================================
# Plugin Category Mapping
# ============================================================================

PLUGIN_CATEGORY_MAP = {
    # Nine Questions
    NINE_QUESTION_Q1: "cognitive",
    NINE_QUESTION_Q2: "cognitive",
    NINE_QUESTION_Q3: "cognitive",
    NINE_QUESTION_Q4: "cognitive",
    NINE_QUESTION_Q5: "cognitive",
    NINE_QUESTION_Q6: "cognitive",
    NINE_QUESTION_Q7: "cognitive",
    NINE_QUESTION_Q8: "cognitive",
    NINE_QUESTION_Q9: "cognitive",
    
    # Cognitive Analysis
    COGNITIVE_BUDGET_CONFLICT: "cognitive",
    COGNITIVE_EXPIRED_ASSUMPTION: "cognitive",
    COGNITIVE_FAILURE_CLUSTER: "cognitive",
    COGNITIVE_SEMANTIC_CONFLICT: "cognitive",
    
    # Memory
    MEMORY_EXTRACTOR: "cognitive",
    
    # Oracle
    ORACLE_ALTERNATIVE: "functional",
    ORACLE_OBJECTIVE: "functional",
    ORACLE_POSTURE: "functional",
    ORACLE_REDLINE: "functional",
    
    # Reflection
    REFLECTION_GENERATOR: "cognitive",
}


def get_plugin_category(plugin_id: str) -> str:
    """
    Get the category of a plugin by its ID.
    
    Args:
        plugin_id: The plugin identifier
        
    Returns:
        Category string ('cognitive', 'functional', etc.)
        
    Raises:
        KeyError: If plugin_id is not recognized
    """
    if plugin_id in PLUGIN_CATEGORY_MAP:
        return PLUGIN_CATEGORY_MAP[plugin_id]
    raise KeyError(f"Unknown plugin_id: {plugin_id}")


def is_cognitive_plugin(plugin_id: str) -> bool:
    """
    Check if a plugin is a cognitive-layer plugin.
    
    Args:
        plugin_id: The plugin identifier
        
    Returns:
        True if the plugin is cognitive-layer, False otherwise
    """
    return plugin_id in ALL_COGNITIVE_PLUGINS


def is_nine_question_plugin(plugin_id: str) -> bool:
    """
    Check if a plugin is one of the nine questions plugins.
    
    Args:
        plugin_id: The plugin identifier
        
    Returns:
        True if the plugin is a nine questions plugin, False otherwise
    """
    return plugin_id in NINE_QUESTIONS_ALL


def get_nine_question_number(plugin_id: str) -> Optional[int]:
    """
    Extract the question number from a nine questions plugin ID.
    
    Args:
        plugin_id: The plugin identifier
        
    Returns:
        Question number (1-9) or None if not a nine questions plugin
    """
    for i, qid in enumerate(NINE_QUESTIONS_ALL, start=1):
        if plugin_id == qid:
            return i
    return None
