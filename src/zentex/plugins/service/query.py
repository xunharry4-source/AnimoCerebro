from __future__ import annotations
"""
Query Service: Plugin Information Retrieval

Handles:
- Query plugins by category/lifecycle/operational dimensions
- Query cognitive plugin's functional plugins
- Get active inventory
- Get execution statistics
- Advanced filtering queries
"""


import logging
from uuid import uuid4
from typing import List, Dict, Any, Optional

from zentex.plugins.models import PluginFeatureCatalogItem, PluginLifecycleStatus

logger = logging.getLogger(__name__)


class QueryService:
    """
    Provides comprehensive plugin querying capabilities.
    
    Responsibilities:
    - Query plugins by various filters
    - Retrieve plugin relationships
    - Get inventory and statistics
    """
    
    def __init__(self, storage, plugin_instances, plugin_specs, execution_stats):
        """
        Initialize query service with references to base service resources.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            plugin_specs: Plugin spec cache
            execution_stats: Execution statistics cache
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._plugin_specs = plugin_specs
        self._execution_stats = execution_stats

    @staticmethod
    def _normalize_lifecycle_status(value: object) -> str:
        return str(getattr(value, "value", value) or "").strip().lower()

    @staticmethod
    def _normalize_operational_status(value: object) -> str:
        return str(value or "").strip().lower()

    def _derive_operational_status(self, record: Dict[str, Any]) -> str:
        """
        Derive runtime status from lifecycle + in-memory runtime state.

        Lifecycle answers "which governance phase is this version in".
        Operational status answers "is this plugin currently usable".

        Rules:
        - non-ACTIVE lifecycle => unavailable
        - ACTIVE + unhealthy/degraded => abnormal
        - ACTIVE + not instantiated or stopped => stopped
        - ACTIVE + healthy runtime => enabled
        """
        plugin_id = str(record.get("plugin_id") or "").strip()
        persisted_operational_status = self._normalize_operational_status(
            record.get("operational_status")
        )
        instance = self._plugin_instances.get(plugin_id)
        health_status = None
        if instance is not None:
            health = getattr(instance, "health_status", None)
            health_status = str(getattr(health, "value", health) or "").strip().lower() or None
        else:
            spec = self._plugin_specs.get(plugin_id, {})
            health = spec.get("health_status") if isinstance(spec, dict) else None
            health_status = str(getattr(health, "value", health) or "").strip().lower() or None

        if bool(record.get("stopped_at")):
            return "stopped"
        lifecycle_status = self._normalize_lifecycle_status(record.get("lifecycle_status"))
        if lifecycle_status != PluginLifecycleStatus.ACTIVE.value:
            return "unavailable"
        if health_status in {"degraded", "unhealthy"}:
            return "abnormal"
        if persisted_operational_status in {"enabled", "stopped", "abnormal"}:
            return persisted_operational_status
        if plugin_id not in self._plugin_instances:
            return "stopped"
        return "enabled"

    def _build_plugin_row(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a standardized plugin row with all UI-required fields.
        
        Includes permission fields (can_force_enable/disable/delete) to avoid
        business logic in web_console layer.
        """
        lifecycle_status = self._normalize_lifecycle_status(record.get("lifecycle_status"))
        operational_status = self._derive_operational_status(record)
        plugin_id = str(record.get("plugin_id") or "").strip()
        is_default = bool(record.get("is_default", False))
        is_active_enabled = (
            lifecycle_status == PluginLifecycleStatus.ACTIVE.value
            and operational_status == "enabled"
        )
        
        return {
            "plugin_id": plugin_id,
            "category": record.get("category"),
            "version": record.get("version"),
            "lifecycle_status": lifecycle_status,
            "operational_status": operational_status,
            "behavior_key": record.get("behavior_key"),
            "feature_code": record.get("feature_code", plugin_id),
            "is_instantiated": plugin_id in self._plugin_instances,
            # Permission fields (migrated from web_console to avoid business logic there)
            "is_default": is_default,
            "can_force_enable": not is_default and not is_active_enabled,
            "can_force_disable": not is_default and is_active_enabled,
            "can_delete": not is_default,
            # UI display fields
            "purpose": record.get("purpose", plugin_id),
            "description": record.get("description", record.get("purpose", plugin_id)),
            "used_in": list(record.get("used_in", []) or []),
            "is_official_release": bool(record.get("is_official_release", True)),
            "rollback_conditions": list(record.get("rollback_conditions", []) or []),
            "trigger_conditions": list(record.get("trigger_conditions", []) or []),
            "required_context": list(record.get("required_context", []) or []),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "started_at": record.get("started_at"),
            "stopped_at": record.get("stopped_at"),
            "usage_count": record.get("usage_count", 0),
            "failure_count": record.get("failure_count", 0),
        }

    def query_by_category(
        self,
        category: str,
        operational_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query all plugins of a specific category.
        
        Args:
            category: 'cognitive', 'functional', 'sensory', etc.
            operational_status: Optional operational filter
            
        Returns:
            List of plugins matching the category
            
        Example:
            >>> cognitive_plugins = service.query_by_category('cognitive')
            >>> enabled_functional = service.query_by_category('functional', 'enabled')
        """
        records = self._storage.list_plugins(category=category)
        target_op = self._normalize_operational_status(operational_status)
        results = []
        
        for record in records:
            if target_op and self._derive_operational_status(record) != target_op:
                continue
                
            results.append({
                "plugin_id": record.get("plugin_id"),
                "category": record.get("category"),
                "version": record.get("version"),
                "lifecycle_status": record.get("lifecycle_status"),
                "operational_status": self._derive_operational_status(record),
                "behavior_key": record.get("behavior_key"),
                "feature_code": record.get("feature_code", record.get("plugin_id")),
                "is_instantiated": record.get("plugin_id") in self._plugin_instances,
            })
        
        logger.info(f"[Query] Found {len(results)} plugins in category '{category}'")
        return results

    def query_plugins_by_lifecycle(
        self,
        *,
        category: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        feature_code: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Query plugins by lifecycle phase.

        This interface is for governance/lifecycle inspection only.
        It does not collapse lifecycle into runtime usability.
        """
        records = self._storage.list_plugins(category=category)
        normalized_lifecycle = self._normalize_lifecycle_status(lifecycle_status)
        results: List[Dict[str, Any]] = []
        for record in records:
            row = self._build_plugin_row(record)
            if normalized_lifecycle and row["lifecycle_status"] != normalized_lifecycle:
                continue
            if behavior_key and row.get("behavior_key") != behavior_key:
                continue
            if feature_code and row.get("feature_code") != feature_code:
                continue
            results.append(row)
            if len(results) >= max(1, min(limit, 500)):
                break
        return results

    def query_plugins_by_operational_status(
        self,
        *,
        category: Optional[str] = None,
        operational_status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        feature_code: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Query plugins by runtime status.

        This interface is for operational usability inspection.
        It keeps lifecycle separate and filters on the derived runtime state:
        enabled / stopped / abnormal / unavailable.
        """
        target_status = self._normalize_operational_status(operational_status)
        records = self._storage.list_plugins(category=category)
        results: List[Dict[str, Any]] = []
        for record in records:
            row = self._build_plugin_row(record)
            if target_status and row["operational_status"] != target_status:
                continue
            if behavior_key and row.get("behavior_key") != behavior_key:
                continue
            if feature_code and row.get("feature_code") != feature_code:
                continue
            results.append(row)
            if len(results) >= max(1, min(limit, 500)):
                break
        return results

    def query_cognitive_functionals_by_lifecycle(
        self,
        cognitive_plugin_id: str,
        *,
        lifecycle_status: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Query functional plugins bound to one cognitive plugin, filtered by lifecycle.

        This API is for relationship governance screens:
        "show me every functional plugin linked to this cognitive plugin, regardless
        of whether it is callable right now, and optionally restrict by lifecycle".
        """
        normalized_lifecycle = self._normalize_lifecycle_status(lifecycle_status)
        relations = self._storage.query_relations_by_cognitive(cognitive_plugin_id)
        results: List[Dict[str, Any]] = []
        for relation in relations:
            functional_plugin = self._storage.get_plugin(relation["functional_plugin_id"])
            if not functional_plugin:
                continue
            row = self._build_plugin_row(functional_plugin)
            if normalized_lifecycle and row["lifecycle_status"] != normalized_lifecycle:
                continue
            if role and relation.get("role") != role:
                continue
            row.update(
                {
                    "role": relation.get("role", "primary"),
                    "priority": relation.get("priority", 1),
                    "fallback_id": relation.get("fallback_id"),
                }
            )
            results.append(row)
            if len(results) >= max(1, min(limit, 500)):
                break
        return results

    def query_cognitive_functionals_by_operational_status(
        self,
        cognitive_plugin_id: str,
        *,
        operational_status: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Query functional plugins bound to one cognitive plugin, filtered by runtime status.

        This API is for operational views:
        "show me which functional plugins under this cognitive plugin are enabled /
        stopped / abnormal / unavailable right now".
        """
        target_status = self._normalize_operational_status(operational_status)
        relations = self._storage.query_relations_by_cognitive(cognitive_plugin_id)
        results: List[Dict[str, Any]] = []
        for relation in relations:
            functional_plugin = self._storage.get_plugin(relation["functional_plugin_id"])
            if not functional_plugin:
                continue
            row = self._build_plugin_row(functional_plugin)
            if target_status and row["operational_status"] != target_status:
                continue
            if role and relation.get("role") != role:
                continue
            row.update(
                {
                    "role": relation.get("role", "primary"),
                    "priority": relation.get("priority", 1),
                    "fallback_id": relation.get("fallback_id"),
                }
            )
            results.append(row)
            if len(results) >= max(1, min(limit, 500)):
                break
        return results

    def query_functional_cognitives(
        self,
        functional_plugin_id: str,
        lifecycle_status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query all cognitive plugins that use a functional plugin.

        Args:
            functional_plugin_id: The functional plugin ID
            lifecycle_status: Optional lifecycle filter

        Returns:
            List of cognitive plugins linked to the functional plugin
        """
        relations = self._storage.query_relations_by_functional(functional_plugin_id)

        results = []
        for relation in relations:
            cognitive_id = relation['cognitive_plugin_id']
            cognitive_plugin = self._storage.get_plugin(cognitive_id)

            if not cognitive_plugin:
                continue

            if lifecycle_status and self._normalize_lifecycle_status(cognitive_plugin.get("lifecycle_status")) != self._normalize_lifecycle_status(lifecycle_status):
                continue

            results.append({
                "cognitive_plugin_id": cognitive_id,
                "functional_plugin_id": functional_plugin_id,
                "role": relation.get('role', 'primary'),
                "priority": relation.get('priority', 1),
                "fallback_id": relation.get('fallback_id'),
                "cognitive_plugin": cognitive_plugin,
            })

        logger.info(f"[Query] Found {len(results)} cognitive plugins for functional '{functional_plugin_id}'")
        return results

    def query_with_filters(
        self,
        category: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        version_gte: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        Advanced query with multiple filters.
        
        Args:
            category: Plugin category filter
            lifecycle_status: Plugin lifecycle filter
            behavior_key: Behavior key filter
            version_gte: Minimum version (semver)
            limit: Maximum results to return
            
        Returns:
            Filtered plugin list with metadata
        """
        target_limit = max(1, min(limit, 500))
        records = self._storage.list_plugins(category=category)
        
        items = []
        for record in records:
            # Apply lifecycle filter
            if lifecycle_status and self._normalize_lifecycle_status(record.get("lifecycle_status")) != self._normalize_lifecycle_status(lifecycle_status):
                continue
                
            # Apply behavior_key filter
            if behavior_key and record.get("behavior_key") != behavior_key:
                continue
                
            # Apply version filter (simple semver comparison)
            if version_gte:
                record_version = record.get("version", "0.0.0")
                if not self._compare_versions(record_version, version_gte):
                    continue
            
            items.append({
                "plugin_id": record.get("plugin_id"),
                "category": record.get("category"),
                "version": record.get("version"),
                "lifecycle_status": record.get("lifecycle_status"),
                "operational_status": self._derive_operational_status(record),
                "behavior_key": record.get("behavior_key"),
                "is_instantiated": record.get("plugin_id") in self._plugin_instances,
            })
        
        logger.info(f"[Query] Advanced filter returned {len(items[:target_limit])} results")
        
        return {
            "query_id": f"plugin-query-{uuid4()}",
            "filters": {
                "category": category,
                "lifecycle_status": lifecycle_status,
                "behavior_key": behavior_key,
                "version_gte": version_gte,
            },
            "total": len(items),
            "items": items[:target_limit],
            "truncated": len(items) > target_limit,
        }

    def get_active_inventory(self) -> List[Dict[str, Any]]:
        """
        Return list of currently ACTIVE plugins.
        This is the current usable plugins list.
        
        Returns:
            List of active plugins with metadata
        """
        records = self._storage.list_plugins()
        active_plugins = []
        
        for r in records:
            if self._normalize_lifecycle_status(r.get("lifecycle_status")) == PluginLifecycleStatus.ACTIVE.value:
                active_plugins.append({
                    "plugin_id": r["plugin_id"],
                    "category": r["category"],
                    "version": r["version"],
                    "lifecycle_status": r["lifecycle_status"],
                    "operational_status": self._derive_operational_status(r),
                    "behavior_key": r["behavior_key"],
                    "feature_code": r.get("feature_code", r["plugin_id"]),
                    "instantiated": r["plugin_id"] in self._plugin_instances,
                })
        
        logger.info(f"[Query] Active inventory: {len(active_plugins)} plugins")
        return active_plugins

    def get_plugin_execution_stats(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get execution statistics for a specific plugin.
        
        Args:
            plugin_id: The plugin identifier
            
        Returns:
            Execution statistics
        """
        if plugin_id not in self._execution_stats:
            db_plugin = self._storage.get_plugin(plugin_id)
            if db_plugin:
                self._execution_stats[plugin_id] = {
                    'usage_count': db_plugin.get('usage_count', 0),
                    'failure_count': db_plugin.get('failure_count', 0),
                    'last_executed_at': None,
                }
            else:
                logger.warning(f"[Query] Plugin {plugin_id} not found")
                return {}
        
        return self._execution_stats[plugin_id]

    def get_aggregated_snapshot(
        self,
        *,
        cognitive_registry: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate plugins from DB, Cognitive Registry, and In-memory instances.
        Relocated logic from web_console for zero-logic UI compliance.
        """
        items: Dict[str, Dict[str, Any]] = {}
        
        # 1. Harvest from Persistent Storage (The Library)
        db_records = self._storage.list_plugins()
        for rec in db_records:
            plugin_id = rec["plugin_id"]
            items[plugin_id] = self._build_plugin_row(rec)
            
        # 2. Merge from Cognitive Registry (The Blueprints)
        if cognitive_registry:
            registrations = []
            if hasattr(cognitive_registry, "list_registrations"):
                registrations = cognitive_registry.list_registrations()
            
            for reg in (registrations or []):
                spec = getattr(reg, "spec", None)
                if not spec: continue
                plugin_id = getattr(spec, "plugin_id", "")
                if not plugin_id: continue
                
                # Overlay registry info
                if plugin_id not in items:
                    items[plugin_id] = {
                        "plugin_id": plugin_id,
                        "category": "cognitive",
                        "is_instantiated": False,
                    }
                items[plugin_id].update({
                    "version": getattr(spec, "version", "1.0.0"),
                    "lifecycle_status": self._normalize_lifecycle_status(getattr(spec, "lifecycle_status", "pending")),
                    "behavior_key": getattr(spec, "behavior_key", None),
                })

        # 3. Merge from Active Instances (The Execution Pool)
        for plugin_id, instance in self._plugin_instances.items():
            if plugin_id not in items:
                items[plugin_id] = {
                    "plugin_id": plugin_id,
                    "is_instantiated": True,
                }
            
            update_payload = {
                "is_instantiated": True,
                "health_status": self._normalize_operational_status(getattr(instance, "health_status", "healthy")),
                "category": getattr(instance, "category", items[plugin_id].get("category", "unknown")),
            }
            if self._normalize_lifecycle_status(items[plugin_id].get("lifecycle_status")) == PluginLifecycleStatus.ACTIVE.value:
                update_payload["operational_status"] = self._normalize_operational_status(
                    getattr(instance, "operational_status", "enabled")
                )
            items[plugin_id].update(update_payload)
            
        return sorted(items.values(), key=lambda x: (x.get("category", ""), x["plugin_id"]))

    def get_sorted_plugin_list(
        self,
        *,
        cognitive_registry: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated snapshot with deterministic sorting.
        
        Sorting rules (migrated from web_console.build_plugin_payloads):
        - Primary: category (plugin_kind)
        - Secondary: feature_code
        - Tertiary: plugin_id
        
        Args:
            cognitive_registry: Optional cognitive registry for merging
            
        Returns:
            Sorted list of plugin data
        """
        snapshot = self.get_aggregated_snapshot(cognitive_registry=cognitive_registry)
        
        # Sort by (category, feature_code, plugin_id)
        return sorted(
            snapshot,
            key=lambda x: (
                x.get("category", ""),
                x.get("feature_code", x.get("plugin_id", "")),
                x.get("plugin_id", "")
            )
        )

    def get_plugins_grouped_by_feature(
        self,
        *,
        cognitive_registry: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        Group all plugins by feature_code with metadata.
        
        Business Logic (migrated from web_console.build_plugin_feature_groups):
        - Groups plugins by feature_code
        - Calculates binding_status based on active plugins
        - Identifies supports_multiple_plugins
        
        Args:
            cognitive_registry: Optional cognitive registry for merging
            
        Returns:
            List of grouped plugin data with structure:
            {
                "feature_code": str,
                "display_name": str,
                "plugin_kind": str,
                "supports_multiple_plugins": bool,
                "binding_status": "active" | "unbound",
                "active_plugin_ids": List[str],
                "plugins": List[Dict]
            }
        """
        all_plugins = self.get_sorted_plugin_list(cognitive_registry=cognitive_registry)
        
        # Group by feature_code
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for plugin in all_plugins:
            feature_code = plugin.get("feature_code", plugin.get("plugin_id", ""))
            groups.setdefault(feature_code, []).append(plugin)
        
        # Build grouped response with metadata
        result = []
        for feature_code, plugins in groups.items():
            if not plugins:
                continue
            
            first_plugin = plugins[0]
            
            # Calculate active plugin IDs
            active_ids = [
                p["plugin_id"] 
                for p in plugins 
                if self._normalize_lifecycle_status(p.get("lifecycle_status")) == PluginLifecycleStatus.ACTIVE.value
            ]
            
            # Determine binding status
            binding_status = "active" if active_ids else "unbound"
            
            result.append({
                "feature_code": feature_code,
                "display_name": first_plugin.get("purpose", first_plugin.get("plugin_id", feature_code)),
                "plugin_kind": first_plugin.get("category", "unknown"),
                "supports_multiple_plugins": len(plugins) > 1,
                "binding_status": binding_status,
                "active_plugin_ids": active_ids,
                "plugins": plugins,
            })
        
        logger.info(f"[Query] Grouped {len(all_plugins)} plugins into {len(result)} feature groups")
        return result

    def get_cognitive_plugin_full_detail(
        self,
        plugin_id: str,
        *,
        cognitive_registry: Any = None,
    ) -> Dict[str, Any]:
        """
        Get complete detail for a cognitive plugin including relationships.
        
        Business Logic (migrated from web_console.build_cognitive_plugin_detail):
        - Finds plugin by ID or feature_code
        - Queries related versions (same feature_code)
        - Queries functional plugin relationships
        - Assembles complete response
        
        Args:
            plugin_id: Plugin ID or feature_code to look up
            cognitive_registry: Optional cognitive registry for merging
            
        Returns:
            Complete plugin detail with structure:
            {
                "plugin": Dict,
                "related_versions": List[Dict],
                "functional_plugins": List[Dict]
            }
            
        Raises:
            KeyError: If plugin not found
        """
        all_plugins = self.get_sorted_plugin_list(cognitive_registry=cognitive_registry)
        
        # Find target plugin (by plugin_id or feature_code)
        target_plugin = None
        for plugin in all_plugins:
            if plugin.get("plugin_id") == plugin_id or plugin.get("feature_code") == plugin_id:
                target_plugin = plugin
                break
        
        if target_plugin is None:
            raise KeyError(f"Plugin not found: {plugin_id}")
        
        target_feature_code = target_plugin.get("feature_code", plugin_id)
        target_plugin_id = target_plugin["plugin_id"]
        
        # Find related versions (same feature_code, different plugin_id)
        related_versions = [
            p for p in all_plugins
            if p.get("feature_code") == target_feature_code
            and p["plugin_id"] != target_plugin_id
        ]
        
        # Query functional plugin relationships
        relations = self._storage.query_relations_by_cognitive(target_plugin_id)
        
        functional_plugins = []
        for relation in relations:
            func_plugin_id = relation["functional_plugin_id"]
            
            # Find functional plugin details from snapshot
            func_plugin = next(
                (p for p in all_plugins if p["plugin_id"] == func_plugin_id),
                None
            )
            
            if func_plugin:
                functional_plugins.append({
                    "plugin": func_plugin,
                    "role": relation.get("role", "primary"),
                    "priority": relation.get("priority", 1),
                    "fallback_id": relation.get("fallback_id"),
                })
        
        return {
            "plugin": target_plugin,
            "related_versions": related_versions,
            "functional_plugins": functional_plugins,
        }

    def get_functional_plugin_full_detail(
        self,
        plugin_id: str,
        *,
        cognitive_registry: Any = None,
    ) -> Dict[str, Any]:
        """
        Get complete detail for a functional plugin including its consumers.
        
        Business Logic (migrated from web_console.build_functional_plugin_detail):
        - Finds functional plugin by ID or feature_code
        - Queries all cognitive plugins that use this functional plugin
        - Assembles complete response with relationship metadata
        
        Args:
            plugin_id: Plugin ID or feature_code to look up
            cognitive_registry: Optional cognitive registry for merging
            
        Returns:
            Complete functional plugin detail with structure:
            {
                "plugin": Dict,
                "cognitive_plugins": List[Dict]
            }
            
        Raises:
            KeyError: If plugin not found
        """
        all_plugins = self.get_sorted_plugin_list(cognitive_registry=cognitive_registry)
        
        # Find target plugin
        target_plugin = None
        for plugin in all_plugins:
            if plugin.get("plugin_id") == plugin_id or plugin.get("feature_code") == plugin_id:
                target_plugin = plugin
                break
        
        if target_plugin is None:
            raise KeyError(f"Plugin not found: {plugin_id}")
        
        target_plugin_id = target_plugin["plugin_id"]
        
        # Query cognitive plugins that use this functional plugin
        relations = self._storage.query_relations_by_functional(target_plugin_id)
        
        cognitive_plugins = []
        for relation in relations:
            cognitive_id = relation["cognitive_plugin_id"]
            
            # Find cognitive plugin details from snapshot
            cognitive_plugin = next(
                (p for p in all_plugins if p["plugin_id"] == cognitive_id),
                None
            )
            
            if cognitive_plugin:
                cognitive_plugins.append({
                    "plugin": cognitive_plugin,
                    "role": relation.get("role", "primary"),
                    "priority": relation.get("priority", 1),
                })
        
        return {
            "plugin": target_plugin,
            "cognitive_plugins": cognitive_plugins,
        }

    def get_force_enable_result(
        self,
        plugin_id: str,
    ) -> Dict[str, Any]:
        """
        Get response data after force-enabling a plugin.
        
        Business Logic (migrated from web_console.build_force_enable_response):
        - Retrieves latest snapshot
        - Finds the enabled plugin
        - Constructs response with metadata
        
        Args:
            plugin_id: The plugin that was force-enabled
            
        Returns:
            Response data for force-enable operation with structure:
            {
                "plugin": Dict,
                "auto_disabled_plugin_ids": List[str],
                "requires_override_warning": bool,
                "message": str
            }
        """
        snapshot = self.get_sorted_plugin_list(cognitive_registry=None)
        
        # Find the plugin
        plugin_data = next(
            (p for p in snapshot if p.get("plugin_id") == plugin_id or p.get("feature_code") == plugin_id),
            None
        )
        
        # Build response
        if plugin_data:
            return {
                "plugin": plugin_data,
                "auto_disabled_plugin_ids": [],  # Future: track auto-disabled plugins
                "requires_override_warning": False,  # Future: detect conflicts
                "message": f"Plugin {plugin_id} force-enabled successfully.",
            }
        
        # Fallback for missing plugin (maintain backward compatibility)
        return {
            "plugin": {
                "plugin_id": plugin_id,
                "feature_code": plugin_id,
                "category": "unknown",
                "lifecycle_status": "active",
                "operational_status": "enabled",
            },
            "auto_disabled_plugin_ids": [],
            "requires_override_warning": False,
            "message": f"Plugin {plugin_id} force-enabled successfully.",
        }

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> bool:
        """
        Simple semantic versioning comparison: v1 >= v2
        
        Args:
            v1: Version string (e.g., "1.2.3")
            v2: Version string (e.g., "1.0.0")
            
        Returns:
            True if v1 >= v2, False otherwise
        """
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]
            
            for p1, p2 in zip(parts1, parts2):
                if p1 > p2:
                    return True
                elif p1 < p2:
                    return False
            
            return len(parts1) >= len(parts2)
        except (ValueError, AttributeError):
            # If parsing fails, assume v1 >= v2 (safe default)
            return True

    def get_feature_catalog(self) -> list:
        """
        Get the feature catalog for all plugin categories.
        
        Returns:
            List of feature catalog items
            
        ⚠️ ARCHITECTURAL: This provides a standardized view of available
        plugin features for UI display.
        """
        # Define standard feature catalog based on plugin categories
        catalog = [
            PluginFeatureCatalogItem(
                feature_code="risk_assessment",
                display_name="风险评估",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="evidence_ranking",
                display_name="证据排序",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="decision_summary",
                display_name="决策摘要",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="cognitive_conflict_detection",
                display_name="认知冲突监控",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="memory_consolidation",
                display_name="离线记忆巩固",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="core.model_provider",
                display_name="大模型推理底座",
                plugin_kind="model_provider",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="sensory.ingest",
                display_name="信号摄取",
                plugin_kind="signal_ingest",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="sensory.sanitize",
                display_name="信号净化",
                plugin_kind="signal_sanitize",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="sensory.interpret",
                display_name="信号解释",
                plugin_kind="signal_interpret",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="host.telemetry",
                display_name="宿主机健康度采集",
                plugin_kind="host_telemetry",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="execution.system",
                display_name="系统执行域",
                plugin_kind="execution_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="execution.browser",
                display_name="浏览器执行域",
                plugin_kind="execution_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="simulation.bundle",
                display_name="通用推演沙箱",
                plugin_kind="simulation_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="simulation.market",
                display_name="市场推演沙箱",
                plugin_kind="simulation_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="weights:subjective_preferences",
                display_name="主观权重偏好",
                plugin_kind="subjective_weight",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="identity:package_loader",
                display_name="身份与经验包",
                plugin_kind="identity_package",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="redline.core",
                display_name="红线禁区基座",
                plugin_kind="redline",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="alternative.core",
                display_name="备选策略基座",
                plugin_kind="alternative",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="objective.core",
                display_name="主目标编排基座",
                plugin_kind="objective",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="posture.core",
                display_name="行动姿态基座",
                plugin_kind="posture",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q1",
                display_name="九问 Q1（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q2",
                display_name="九问 Q2（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q3",
                display_name="九问 Q3（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q4",
                display_name="九问 Q4（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q5",
                display_name="九问 Q5（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q6",
                display_name="九问 Q6（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q7",
                display_name="九问 Q7（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q8",
                display_name="九问 Q8（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q9",
                display_name="九问 Q9（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="memory.extract",
                display_name="记忆提取（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="reflection.generate",
                display_name="反思生成（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
        ]
        return catalog
