"""
Phase B1: Task dispatch and execution routing subpackage.

Responsible for selecting and executing tasks on appropriate executors
(internal FUNCTIONAL plugins or external MCP/AGENT/CLI).

Routing Policy (per requirements):
- Internal: PluginLayer.FUNCTIONAL plugins have highest priority
- External: MCP/AGENT/CLI executors ranked by credit/quality evidence
- Fallback: Try internal first; if no match, escalate to external
"""

from zentex.tasks.dispatch.models import (
    ExecutorType,
    ExecutorCandidate,
    DispatchDecision,
    DispatchResult,
)
from zentex.tasks.dispatch.router import TaskRouter
from zentex.tasks.dispatch.internal import InternalPluginExecutor
from zentex.tasks.dispatch.router_impl import UnifiedTaskRouter
from zentex.tasks.dispatch.registry import ExecutorRegistry

__all__ = [
    "ExecutorType",
    "ExecutorCandidate",
    "DispatchDecision",
    "DispatchResult",
    "TaskRouter",
    "InternalPluginExecutor",
    "UnifiedTaskRouter",
    "ExecutorRegistry",
]
