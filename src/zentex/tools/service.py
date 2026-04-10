from __future__ import annotations

"""
Zentex Tools Service Facade.

Manages the registration and execution of internal and external tools (MCP, Domain Tools).
Provides a unified interface for agent reasoning loops to discover and invoke actions.
"""

import logging
from typing import Any, Dict, List, Optional

from zentex.core.execution_registry import ExecutionDomainRegistry
from zentex.core.execution_spec import ExecutionDomainPlugin

logger = logging.getLogger(__name__)


class ToolService:
    """
    Gateway service for Zentex Tool Registry.
    
    Coordinates tool discovery, validation, and dispatcher registration.
    """

    def __init__(self, registry: Optional[ExecutionDomainRegistry] = None) -> None:
        self._registry = registry or ExecutionDomainRegistry()
        logger.info("ToolService initialized")

    def register_tool_plugin(self, plugin: ExecutionDomainPlugin, **kwargs) -> Any:
        """Register a new execution domain plugin as a candidate."""
        return self._registry.register(plugin, **kwargs)

    def list_tools(self) -> List[Any]:
        """List all registered execution domains and their capabilities."""
        return self._registry.list_registrations()

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic health and registration totals for the tool system."""
        tools = self.list_tools()
        return {
            "total_registered_tools": len(tools),
            "tool_registry_kind": "ExecutionDomainRegistry",
            "active_tools": [t.plugin_id for t in tools if t.spec.status == "active"]
        }


# Global singleton instance
_default_service: Optional[ToolService] = None


def get_tool_service() -> ToolService:
    """Return the shared global instance of the ToolService."""
    global _default_service
    if _default_service is None:
        _default_service = ToolService()
    return _default_service
