"""
Plugin Manager: Unified Service Entry Point

Combines all services (base, query, execute, manage) into one coherent interface.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.manager import PluginManager
from zentex.common.protocol import TaskEnvelope, TaskFeedback

from .base import BasePluginService
from .query import QueryService
from .execute import ExecutionService
from .manage import ManagementService
from .upgrade import UpgradeService
from .info import InfoService
from .test import TestService

logger = logging.getLogger(__name__)


class SystemPluginService(BasePluginService):
    """
    Complete plugin governance service combining all sub-services.
    
    This is the main entry point for all plugin operations:
    - Bootstrap and initialization (base)
    - Querying and discovery (query)
    - Execution and validation (execute)
    - Management and lifecycle (manage)
    """
    
    def __init__(
        self,
        db_path: str,
        manager: Optional[PluginManager] = None,
    ) -> None:
        """
        Initialize the unified plugin service.
        
        Args:
            db_path: Path to SQLite database
            manager: Optional PluginManager reference
        """
        # Initialize base service
        super().__init__(db_path=db_path, manager=manager)
        
        # Initialize sub-services
        self._query_service = QueryService(
            storage=self._storage,
            plugin_instances=self._plugin_instances,
            plugin_specs=self._plugin_specs,
            execution_stats=self._execution_stats,
        )
        
        self._execution_service = ExecutionService(
            storage=self._storage,
            plugin_instances=self._plugin_instances,
            execution_stats=self._execution_stats,
            determine_category_fn=self._determine_category,
            promote_fn=self._promote_plugin_ref,
        )
        
        self._management_service = ManagementService(
            storage=self._storage,
            plugin_instances=self._plugin_instances,
            plugin_specs=self._plugin_specs,
            get_factories_fn=self._get_factories,
            determine_category_fn=self._determine_category,
        )
        
        # Initialize Phase 2c services
        self._upgrade_service = UpgradeService(
            storage=self._storage,
            plugin_instances=self._plugin_instances,
            execution_service=self._execution_service,
            query_service=self._query_service,
            determine_category_fn=self._determine_category,
        )
        
        self._info_service = InfoService(
            storage=self._storage,
            plugin_instances=self._plugin_instances,
            query_service=self._query_service,
            determine_category_fn=self._determine_category,
        )
        
        self._test_service = TestService(
            storage=self._storage,
            plugin_instances=self._plugin_instances,
            execution_service=self._execution_service,
            query_service=self._query_service,
            determine_category_fn=self._determine_category,
        )
    
    def _promote_plugin_ref(self, plugin_id: str, target_status, reason: str) -> None:
        """Helper reference for auto-degradation."""
        self._management_service.promote_plugin(plugin_id, target_status, reason)
    
    # ==================== Query Service Methods ====================
    
    def query_by_category(
        self,
        category: str,
        status: Optional[str] = None,
    ) -> list:
        """Query plugins by category."""
        return self._query_service.query_by_category(category, status)
    
    def query_cognitive_functionals(
        self,
        cognitive_plugin_id: str,
        status: Optional[str] = None,
    ) -> list:
        """Query functional plugins for a cognitive plugin."""
        return self._query_service.query_cognitive_functionals(cognitive_plugin_id, status)
    
    def query_with_filters(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        version_gte: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """Advanced query with multiple filters."""
        return self._query_service.query_with_filters(
            category=category,
            status=status,
            behavior_key=behavior_key,
            version_gte=version_gte,
            limit=limit,
        )
    
    def get_active_inventory(self) -> list:
        """Get all active plugins."""
        return self._query_service.get_active_inventory()
    
    def get_plugin_execution_stats(self, plugin_id: str) -> Dict[str, Any]:
        """Get execution stats for a plugin."""
        return self._query_service.get_plugin_execution_stats(plugin_id)
    
    def query_plugins(
        self,
        *,
        category: Optional[str] = None,
        status: str = PluginLifecycleStatus.ACTIVE.value,
        behavior_key: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """Query plugins (backward compatible API)."""
        return self._query_service.query_plugins(
            category=category,
            status=status,
            behavior_key=behavior_key,
            limit=limit,
        )
    
    # ==================== Execute Service Methods ====================
    
    async def execute_plugin_once(
        self,
        *,
        plugin_id: str,
        task_id: str,
        parameters: Dict[str, Any],
        trace_id: str,
        originator_id: str,
        caller_plugin_id: Optional[str] = None,
    ) -> TaskFeedback:
        """Execute a single plugin."""
        return await self._execution_service.execute_plugin_once(
            plugin_id=plugin_id,
            task_id=task_id,
            parameters=parameters,
            trace_id=trace_id,
            originator_id=originator_id,
            caller_plugin_id=caller_plugin_id,
        )
    
    # ==================== Management Service Methods ====================
    
    def promote_plugin(
        self,
        plugin_id: str,
        target_status: PluginLifecycleStatus,
        reason: str,
    ) -> None:
        """Promote plugin to new status."""
        self._management_service.promote_plugin(plugin_id, target_status, reason)
    
    def enable_plugin(self, plugin_id: str, reason: str = "Manual activation") -> None:
        """Enable a plugin."""
        self._management_service.enable_plugin(plugin_id, reason)
    
    def disable_plugin(self, plugin_id: str, reason: str = "Manual deactivation") -> None:
        """Disable a plugin."""
        self._management_service.disable_plugin(plugin_id, reason)
    
    def batch_disable(
        self,
        cognitive_plugin_id: Optional[str] = None,
        category: Optional[str] = None,
        behavior_key: Optional[str] = None,
        reason: str = "Batch deactivation",
    ) -> list:
        """Disable multiple plugins."""
        return self._management_service.batch_disable(
            cognitive_plugin_id=cognitive_plugin_id,
            category=category,
            behavior_key=behavior_key,
            reason=reason,
        )
    
    def bind_cognitive_functional(
        self,
        cognitive_plugin_id: str,
        functional_plugin_id: str,
        role: str = "primary",
        priority: int = 1,
        fallback_id: Optional[str] = None,
    ) -> None:
        """Bind a functional plugin to a cognitive plugin."""
        self._management_service.bind_cognitive_functional(
            cognitive_plugin_id=cognitive_plugin_id,
            functional_plugin_id=functional_plugin_id,
            role=role,
            priority=priority,
            fallback_id=fallback_id,
        )
    
    def unbind_cognitive_functional(
        self,
        cognitive_plugin_id: str,
        functional_plugin_id: str,
    ) -> None:
        """Unbind a functional plugin from a cognitive plugin."""
        self._management_service.unbind_cognitive_functional(
            cognitive_plugin_id=cognitive_plugin_id,
            functional_plugin_id=functional_plugin_id,
        )
    
    def register_plugin(
        self,
        plugin_id: str,
        plugin_instance: Any,
        category: str,
        version: str = "1.0.0",
        behavior_key: Optional[str] = None,
    ) -> None:
        """Register a plugin manually."""
        self._management_service.register_plugin(
            plugin_id=plugin_id,
            plugin_instance=plugin_instance,
            category=category,
            version=version,
            behavior_key=behavior_key,
        )
    
    # ==================== Public Task Handler ====================
    
    async def handle_task(self, envelope: TaskEnvelope) -> TaskFeedback:
        """
        ZTP Implementation: Standardized task entry point for Plugin Pillar.
        Supports call hierarchy validation via 'caller_plugin_id' parameter.
        """
        plugin_id = envelope.parameters.get("plugin_id")
        if not plugin_id:
            return TaskFeedback(
                task_id=envelope.task_id,
                status="failed",
                error="Missing 'plugin_id' in task parameters",
                remarks="Plugin Pillar requires 'plugin_id' parameter."
            )

        # Extract optional caller_plugin_id for constraint checking
        caller_plugin_id = envelope.parameters.get("caller_plugin_id")

        return await self.execute_plugin_once(
            plugin_id=plugin_id,
            task_id=envelope.task_id,
            parameters=envelope.parameters,
            trace_id=envelope.trace_id,
            originator_id=envelope.originator_id,
            caller_plugin_id=caller_plugin_id,
        )
    
    # ==================== Upgrade Service Methods ====================
    
    def check_updates(self, plugin_id: str) -> list:
        """Check for available plugin updates."""
        return self._upgrade_service.check_updates(plugin_id)
    
    async def upgrade_plugin(
        self,
        plugin_id: str,
        target_version: str,
        reason: str = "Plugin upgrade",
    ) -> bool:
        """Upgrade plugin to target version."""
        return await self._upgrade_service.upgrade_plugin(
            plugin_id=plugin_id,
            target_version=target_version,
            reason=reason,
        )
    
    async def rollback_plugin(
        self,
        plugin_id: str,
        reason: str = "Manual rollback",
    ) -> bool:
        """Rollback plugin to previous version."""
        return await self._upgrade_service.rollback_plugin(
            plugin_id=plugin_id,
            reason=reason,
        )
    
    def get_upgrade_status(self, plugin_id: str):
        """Get upgrade status for plugin."""
        return self._upgrade_service.get_upgrade_status(plugin_id)
    
    def get_upgrade_history(self, plugin_id: str) -> list:
        """Get upgrade history for plugin."""
        return self._upgrade_service.get_upgrade_history(plugin_id)
    
    def get_all_upgradeable_plugins(self) -> list:
        """Get all plugins with available updates."""
        return self._upgrade_service.get_all_upgradeable_plugins()
    
    # ==================== Info Service Methods ====================
    
    def get_plugin_documentation(self, plugin_id: str):
        """Get documentation for a plugin."""
        return self._info_service.get_plugin_documentation(plugin_id)
    
    def get_plugin_protocol(self, plugin_id: str) -> dict:
        """Get protocol/interface information for a plugin."""
        return self._info_service.get_plugin_protocol(plugin_id)
    
    def get_plugin_rules(self, plugin_id: str) -> dict:
        """Get classification and execution rules for a plugin."""
        return self._info_service.get_plugin_rules(plugin_id)
    
    def get_plugin_capabilities(self, plugin_id: str) -> list:
        """Get list of plugin capabilities."""
        return self._info_service.get_plugin_capabilities(plugin_id)
    
    def get_compatibility_matrix(self) -> dict:
        """Get compatibility matrix for all plugins."""
        return self._info_service.get_compatibility_matrix()
    
    def get_plugin_summary(self, plugin_id: str) -> dict:
        """Get complete summary of plugin information."""
        return self._info_service.get_plugin_summary(plugin_id)
    
    # ==================== Test Service Methods ====================
    
    async def run_health_check(self, plugin_id: str = None):
        """Run health checks on plugins."""
        return await self._test_service.health_check(plugin_id)
    
    async def run_compatibility_test(self, plugin_id: str = None):
        """Test plugin compatibility and constraint satisfaction."""
        return await self._test_service.compatibility_test(plugin_id)
    
    async def run_stress_test(
        self,
        plugin_id: str,
        iterations: int = 100,
        concurrent: bool = False,
    ):
        """Run stress test on a plugin."""
        return await self._test_service.stress_test(
            plugin_id=plugin_id,
            iterations=iterations,
            concurrent=concurrent,
        )
    
    async def generate_test_report(self) -> dict:
        """Generate comprehensive test report."""
        return await self._test_service.generate_test_report()
    
    # ==================== Web Console Integration Methods ====================
    
    def get_all_plugins(self) -> Dict[str, Any]:
        """
        Get all registered plugins for web console display.
        
        This is the ONLY way external modules should access the plugin registry.
        Never import zentex.plugins.builtin.* directly.
        
        Returns:
            Dictionary mapping plugin_id to plugin info
            
        Example:
            from zentex.plugins.service import SystemPluginService
            service = SystemPluginService(db_path=".zentex/plugins.db")
            service.bootstrap()
            plugins = service.get_all_plugins()
        """
        return self._query_service.get_all_plugins()
    
    def get_feature_catalog(self):
        """
        Get feature catalog for web console display.
        
        This provides a standardized view of available plugin features.
        
        Returns:
            List of PluginFeatureCatalogItem
            
        Example:
            catalog = service.get_feature_catalog()
        """
        return self._query_service.get_feature_catalog()


# Backward compatibility alias
class PluginGovernanceService(SystemPluginService):
    """Backward compatible alias for SystemPluginService."""
    pass
