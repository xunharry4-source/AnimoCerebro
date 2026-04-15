"""
Plugin Manager: Unified Service Entry Point

Combines all services (base, query, execute, manage) into one coherent interface.
"""

from __future__ import annotations

import logging
import threading
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from zentex.foundation.contracts import ServiceErrorCode, ServiceResponse
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


def _feedback_to_service_response(feedback: TaskFeedback, *, trace_id: str) -> ServiceResponse:
    result = feedback.result
    if isinstance(result, dict) and set(result.keys()) == {"value"}:
        result = result["value"]

    if feedback.status == "done":
        return ServiceResponse.ok(
            data=result,
            trace_id=trace_id,
            audit_ref=str(getattr(feedback, "task_id", "") or ""),
        )

    error = str(getattr(feedback, "error", "") or "")
    code_map = {
        "plugin_not_found": ServiceErrorCode.INVALID_ARGUMENT,
        "plugin_not_active": ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
        "plugin_not_enabled": ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
        "plugin_not_instantiated": ServiceErrorCode.DEPENDENCY_UNAVAILABLE,
        "execution_error": ServiceErrorCode.INTERNAL_UNRECOVERABLE,
    }
    return ServiceResponse.error(
        code_map.get(error, ServiceErrorCode.INTERNAL_UNRECOVERABLE),
        message=str(getattr(feedback, "remarks", "") or error or "Plugin execution failed"),
        trace_id=trace_id,
        audit_ref=str(getattr(feedback, "task_id", "") or ""),
        data=result,
    )


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
            public_service=self,
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
    
    def _promote_plugin_ref(self, plugin_id: str, target_lifecycle_status: str, reason: str) -> None:
        """Helper reference for auto-degradation."""
        self._management_service.promote_plugin(plugin_id, target_lifecycle_status, reason)
    
    # ==================== Query Service Methods ====================
    
    def query_by_category(
        self,
        category: str,
        operational_status: Optional[str] = None,
    ) -> list:
        """Query plugins by category."""
        return self._query_service.query_by_category(category, operational_status)

    def query_plugins_by_lifecycle(
        self,
        *,
        category: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        feature_code: Optional[str] = None,
        limit: int = 200,
    ) -> list:
        """Query plugins by lifecycle phase without collapsing into runtime state."""
        return self._query_service.query_plugins_by_lifecycle(
            category=category,
            lifecycle_status=lifecycle_status,
            behavior_key=behavior_key,
            feature_code=feature_code,
            limit=limit,
        )

    def query_plugins_by_operational_status(
        self,
        *,
        category: Optional[str] = None,
        operational_status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        feature_code: Optional[str] = None,
        limit: int = 200,
    ) -> list:
        """Query plugins by runtime status (enabled/stopped/abnormal/unavailable)."""
        return self._query_service.query_plugins_by_operational_status(
            category=category,
            operational_status=operational_status,
            behavior_key=behavior_key,
            feature_code=feature_code,
            limit=limit,
        )
    
    def query_cognitive_functionals_by_lifecycle(
        self,
        cognitive_plugin_id: str,
        *,
        lifecycle_status: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 200,
    ) -> list:
        """Query one cognitive plugin's functional plugins by lifecycle."""
        return self._query_service.query_cognitive_functionals_by_lifecycle(
            cognitive_plugin_id,
            lifecycle_status=lifecycle_status,
            role=role,
            limit=limit,
        )

    def query_cognitive_functionals_by_operational_status(
        self,
        cognitive_plugin_id: str,
        *,
        operational_status: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 200,
    ) -> list:
        """Query one cognitive plugin's functional plugins by runtime status."""
        return self._query_service.query_cognitive_functionals_by_operational_status(
            cognitive_plugin_id,
            operational_status=operational_status,
            role=role,
            limit=limit,
        )

    def query_functional_cognitives(
        self,
        functional_plugin_id: str,
        lifecycle_status: Optional[str] = None,
    ) -> list:
        """Query cognitive plugins for a functional plugin."""
        return self._query_service.query_functional_cognitives(
            functional_plugin_id,
            lifecycle_status=lifecycle_status,
        )
    
    def query_with_filters(
        self,
        category: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        version_gte: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """Advanced query with multiple filters."""
        return self._query_service.query_with_filters(
            category=category,
            lifecycle_status=lifecycle_status,
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

    def get_aggregated_snapshot(self, *, cognitive_registry: Any = None) -> list:
        """Get aggregated snapshot from all sources (DB, Registry, Memory)."""
        return self._query_service.get_aggregated_snapshot(cognitive_registry=cognitive_registry)

    def get_sorted_plugin_list(self, *, cognitive_registry: Any = None) -> list:
        """Get sorted plugin list."""
        return self._query_service.get_sorted_plugin_list(cognitive_registry=cognitive_registry)

    def get_plugins_grouped_by_feature(self, *, cognitive_registry: Any = None) -> list:
        """Get plugins grouped by feature."""
        return self._query_service.get_plugins_grouped_by_feature(cognitive_registry=cognitive_registry)

    def get_cognitive_plugin_full_detail(
        self,
        plugin_id: str,
        *,
        cognitive_registry: Any = None,
    ) -> Dict[str, Any]:
        """Get cognitive plugin full detail."""
        return self._query_service.get_cognitive_plugin_full_detail(
            plugin_id,
            cognitive_registry=cognitive_registry
        )

    def get_functional_plugin_full_detail(
        self,
        plugin_id: str,
        *,
        cognitive_registry: Any = None,
    ) -> Dict[str, Any]:
        """Get functional plugin full detail."""
        return self._query_service.get_functional_plugin_full_detail(
            plugin_id,
            cognitive_registry=cognitive_registry
        )

    def get_force_enable_result(self, plugin_id: str) -> Dict[str, Any]:
        """Get force enable result."""
        return self._query_service.get_force_enable_result(plugin_id)
    
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

    def execute_plugin_once_sync(
        self,
        *,
        plugin_id: str,
        task_id: str,
        parameters: Dict[str, Any],
        trace_id: str,
        originator_id: str,
        caller_plugin_id: Optional[str] = None,
    ) -> TaskFeedback:
        """Synchronous wrapper for callers that cannot `await` plugin execution."""

        async def _runner() -> TaskFeedback:
            return await self.execute_plugin_once(
                plugin_id=plugin_id,
                task_id=task_id,
                parameters=parameters,
                trace_id=trace_id,
                originator_id=originator_id,
                caller_plugin_id=caller_plugin_id,
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_runner())

        result: Dict[str, TaskFeedback] = {}
        error: Dict[str, BaseException] = {}

        def _thread_target() -> None:
            try:
                result["feedback"] = asyncio.run(_runner())
            except BaseException as exc:  # pragma: no cover - defensive bridge
                error["exception"] = exc

        thread = threading.Thread(target=_thread_target, daemon=True)
        thread.start()
        thread.join()

        if "exception" in error:
            raise error["exception"]
        return result["feedback"]

    def query_enabled_functional_plugins_for_cognitive(
        self,
        cognitive_plugin_id: str,
        *,
        role: Optional[str] = None,
        limit: int = 200,
        trace_id: str = "",
    ) -> ServiceResponse:
        """Return enabled functional bindings for one cognitive plugin."""
        try:
            rows = self.query_cognitive_functionals_by_operational_status(
                cognitive_plugin_id,
                operational_status="enabled",
                role=role,
                limit=limit,
            )
            return ServiceResponse.ok(data=rows, trace_id=trace_id)
        except Exception as exc:
            return ServiceResponse.error(
                ServiceErrorCode.INTERNAL_UNRECOVERABLE,
                message=f"Failed querying enabled functional plugins: {exc}",
                trace_id=trace_id,
            )

    def execute_functional_plugin(
        self,
        *,
        plugin_id: str,
        context: Dict[str, Any],
        caller_plugin_id: str,
        trace_id: str = "",
        originator_id: str = "",
    ) -> ServiceResponse:
        """Execute one functional plugin through the canonical service boundary."""
        plugin = self._storage.get_plugin(plugin_id)
        if not plugin:
            return ServiceResponse.error(
                ServiceErrorCode.INVALID_ARGUMENT,
                message=f"Unknown functional plugin: {plugin_id}",
                trace_id=trace_id,
            )
        if str(plugin.get("category") or "").strip().lower() == "cognitive":
            return ServiceResponse.error(
                ServiceErrorCode.INVALID_ARGUMENT,
                message=f"Plugin {plugin_id} is cognitive, not functional",
                trace_id=trace_id,
            )

        effective_trace_id = trace_id or str(context.get("trace_id") or "")
        feedback = self.execute_plugin_once_sync(
            plugin_id=plugin_id,
            task_id=f"{effective_trace_id or 'functional'}:{plugin_id}",
            parameters=dict(context),
            trace_id=effective_trace_id or plugin_id,
            originator_id=originator_id or caller_plugin_id,
            caller_plugin_id=caller_plugin_id,
        )
        return _feedback_to_service_response(feedback, trace_id=effective_trace_id or plugin_id)

    def execute_cognitive_plugin(
        self,
        *,
        plugin_id: str,
        context: Dict[str, Any],
        session_id: str = "",
        turn_id: str = "",
        trace_id: str = "",
        originator_id: str = "",
    ) -> ServiceResponse:
        """Execute one cognitive plugin through the canonical service boundary."""
        plugin = self._storage.get_plugin(plugin_id)
        if not plugin:
            return ServiceResponse.error(
                ServiceErrorCode.INVALID_ARGUMENT,
                message=f"Unknown cognitive plugin: {plugin_id}",
                trace_id=trace_id,
            )
        if str(plugin.get("category") or "").strip().lower() != "cognitive":
            return ServiceResponse.error(
                ServiceErrorCode.INVALID_ARGUMENT,
                message=f"Plugin {plugin_id} is not a cognitive plugin",
                trace_id=trace_id,
            )

        payload = dict(context)
        if session_id:
            payload.setdefault("session_id", session_id)
        if turn_id:
            payload.setdefault("turn_id", turn_id)

        effective_trace_id = trace_id or str(payload.get("trace_id") or "")
        feedback = self.execute_plugin_once_sync(
            plugin_id=plugin_id,
            task_id=f"{effective_trace_id or 'cognitive'}:{plugin_id}",
            parameters=payload,
            trace_id=effective_trace_id or plugin_id,
            originator_id=originator_id or session_id or "kernel",
            caller_plugin_id=None,
        )
        return _feedback_to_service_response(feedback, trace_id=effective_trace_id or plugin_id)
    
    # ==================== Management Service Methods ====================
    
    def promote_plugin(
        self,
        plugin_id: str,
        target_lifecycle_status: PluginLifecycleStatus,
        reason: str,
    ) -> None:
        """Promote plugin to new status."""
        self._management_service.promote_plugin(plugin_id, target_lifecycle_status, reason)
    
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

    def activate_all_functional(
        self,
        reason: str = "Bulk functional plugin activation",
    ) -> dict:
        """Activate all registered functional plugins that are not yet ACTIVE.

        Returns a summary dict with keys: activated, already_active,
        skipped_cognitive, failed.
        """
        return self._management_service.activate_all_functional(reason=reason)

    def activate_all_cognitive(
        self,
        reason: str = "Bulk cognitive plugin activation",
    ) -> dict:
        """Activate all registered cognitive plugins while preserving blue-green semantics."""
        return self._management_service.activate_all_cognitive(reason=reason)

    def ensure_runtime_instance_loaded(self, plugin_id: str) -> bool:
        """
        On-demand instantiation for ACTIVE plugins.
        Checks library/storage and instantiates if missing from memory.
        """
        return self._management_service._ensure_runtime_instance_loaded(plugin_id)

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

    def scan_orphaned_plugin_records(self) -> list[dict[str, Any]]:
        """List registered plugins whose implementations are no longer discoverable."""
        available_plugin_ids = set(self._get_factories().keys())
        orphaned: list[dict[str, Any]] = []
        for plugin in self._storage.list_plugins():
            plugin_id = str(plugin.get("plugin_id") or "").strip()
            if plugin_id and plugin_id not in available_plugin_ids:
                orphaned.append(plugin)
        return orphaned

    def reconcile_orphaned_plugin_records(self, *, reason: str) -> dict[str, Any]:
        """
        Mark orphaned plugin records as stopped/degraded without deleting history.

        This is an explicit governance action and never runs during bootstrap.
        """
        orphaned_plugin_ids: list[str] = []
        now = datetime.now(timezone.utc).isoformat()
        for plugin in self.scan_orphaned_plugin_records():
            plugin_id = str(plugin["plugin_id"])
            spec_dict = json.loads(plugin["spec_json"])
            spec_dict["lifecycle_status"] = PluginLifecycleStatus.DEGRADED.value
            spec_dict["operational_status"] = "stopped"
            self._storage.upsert_plugin(
                category=plugin["category"],
                plugin_id=plugin_id,
                spec_dict=spec_dict,
                registration_dict={
                    **plugin,
                    "lifecycle_status": PluginLifecycleStatus.DEGRADED.value,
                    "operational_status": "stopped",
                    "updated_at": now,
                    "stopped_at": now,
                },
            )
            self._plugin_instances.pop(plugin_id, None)
            self._plugin_specs[plugin_id] = spec_dict
            orphaned_plugin_ids.append(plugin_id)

        return {
            "orphaned_plugin_ids": orphaned_plugin_ids,
            "orphaned_count": len(orphaned_plugin_ids),
            "reason": reason,
        }
    
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
    
    def list_plugin_instances(self) -> list[Any]:
        """
        Return all managed plugin instances through the public service boundary.

        External callers must not read `_plugin_instances` directly.
        """
        unique_instances: list[Any] = []
        seen_instance_ids: set[int] = set()
        for plugin in self._plugin_instances.values():
            plugin_id = str(getattr(plugin, "plugin_id", "") or "").strip()
            if not plugin_id:
                continue
            marker = id(plugin)
            if marker in seen_instance_ids:
                continue
            seen_instance_ids.add(marker)
            unique_instances.append(plugin)
        return unique_instances
    
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
