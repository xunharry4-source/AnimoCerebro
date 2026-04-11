"""
Management Service: Plugin Lifecycle and Relationship Management

Handles:
- Plugin promotion (status transitions)
- Plugin registration (manual)
- Enabling/disabling plugins
- Managing plugin relationships
- Conflict detection and resolution
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class ManagementService:
    """
    Provides plugin lifecycle management and relationship management.
    
    Responsibilities:
    - Manage plugin state transitions
    - Register plugins manually
    - Enable/disable plugins
    - Manage cognitive→functional relationships
    - Handle conflicts and dependencies
    """
    
    def __init__(self, storage, plugin_instances, plugin_specs, get_factories_fn, determine_category_fn):
        """
        Initialize management service.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            plugin_specs: Plugin spec cache
            get_factories_fn: Function to get plugin factories
            determine_category_fn: Function to determine plugin category
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._plugin_specs = plugin_specs
        self._get_factories = get_factories_fn
        self._determine_category = determine_category_fn

    def promote_plugin(
        self,
        plugin_id: str,
        target_status: PluginLifecycleStatus,
        reason: str
    ) -> None:
        """
        Promote a plugin to a new state.
        
        State transitions:
        - CANDIDATE → SANDBOX_VERIFIED → ACTIVE ↔ DEGRADED → REVOKED
        
        Args:
            plugin_id: Plugin to promote
            target_status: Target lifecycle status
            reason: Reason for promotion (for audit log)
            
        Raises:
            KeyError: If plugin not found
        """
        plugin = self._storage.get_plugin(plugin_id)
        if not plugin:
            raise KeyError(f"Plugin {plugin_id} not found in database.")

        # If promoting to ACTIVE, deactivate conflicting plugins
        if target_status == PluginLifecycleStatus.ACTIVE:
            self._deactivate_conflicting_plugins(plugin_id, plugin.get("behavior_key"), reason)

        now = datetime.now(timezone.utc).isoformat()
        
        # Update spec status
        spec_dict = json.loads(plugin["spec_json"])
        spec_dict["status"] = target_status.value
        
        # Update registration metadata
        registration_update = {
            "status": target_status.value,
            "updated_at": now
        }
        if target_status == PluginLifecycleStatus.ACTIVE:
            registration_update["started_at"] = now
            registration_update["stopped_at"] = None
        elif target_status in {PluginLifecycleStatus.REVOKED, PluginLifecycleStatus.DEGRADED}:
            registration_update["stopped_at"] = now

        # Persist to database
        self._storage.upsert_plugin(
            category=plugin["category"],
            plugin_id=plugin_id,
            spec_dict=spec_dict,
            registration_dict={**plugin, **registration_update}
        )
        
        # Update memory registry
        self._plugin_specs[plugin_id] = spec_dict
        
        if target_status == PluginLifecycleStatus.ACTIVE:
            # Try to instantiate if not already in memory
            if plugin_id not in self._plugin_instances:
                factory = self._get_factories().get(plugin_id)
                if factory:
                    try:
                        self._plugin_instances[plugin_id] = factory()
                    except Exception as e:
                        logger.warning(f"[Plugins] Failed to instantiate {plugin_id} during promotion: {e}")
        elif plugin_id in self._plugin_instances:
            # Keep instance in memory but mark as inactive
            pass
            
        logger.info(f"[Plugins] {plugin_id} promoted to {target_status.value}. Reason: {reason}")

    def enable_plugin(self, plugin_id: str, reason: str = "Manual activation") -> None:
        """
        Enable (activate) a plugin.
        
        Args:
            plugin_id: Plugin to enable
            reason: Reason for enabling
        """
        self.promote_plugin(plugin_id, PluginLifecycleStatus.ACTIVE, reason)

    def disable_plugin(self, plugin_id: str, reason: str = "Manual deactivation") -> None:
        """
        Disable (degrade) a plugin.
        
        Args:
            plugin_id: Plugin to disable
            reason: Reason for disabling
        """
        self.promote_plugin(plugin_id, PluginLifecycleStatus.DEGRADED, reason)

    def batch_disable(
        self,
        cognitive_plugin_id: Optional[str] = None,
        category: Optional[str] = None,
        behavior_key: Optional[str] = None,
        reason: str = "Batch deactivation",
    ) -> List[str]:
        """
        Disable multiple plugins at once.
        
        Args:
            cognitive_plugin_id: If specified, disable all functional plugins for this cognitive plugin
            category: If specified, disable all plugins of this category
            behavior_key: If specified, disable all plugins with this behavior key
            reason: Reason for disabling
            
        Returns:
            List of disabled plugin IDs
            
        Example:
            >>> disabled = service.batch_disable(cognitive_plugin_id='q1_where_am_i')
            >>> disabled = service.batch_disable(category='functional')
        """
        all_plugins = self._storage.list_plugins()
        disabled = []
        
        for plugin in all_plugins:
            should_disable = False
            
            if cognitive_plugin_id:
                # Disable all functional plugins for this cognitive
                # Get all functionals linked to this cognitive via plugin_relations
                relations = self._storage.query_relations_by_cognitive(cognitive_plugin_id)
                functional_ids = {r['functional_plugin_id'] for r in relations}
                
                if plugin['plugin_id'] in functional_ids:
                    should_disable = True
                    
            if category and plugin['category'] == category:
                should_disable = True
                
            if behavior_key and plugin.get('behavior_key') == behavior_key:
                should_disable = True
            
            if should_disable and plugin['status'] == PluginLifecycleStatus.ACTIVE.value:
                try:
                    self.disable_plugin(plugin['plugin_id'], reason)
                    disabled.append(plugin['plugin_id'])
                except Exception as e:
                    logger.error(f"[Plugins] Failed to disable {plugin['plugin_id']}: {e}")
        
        logger.info(f"[Plugins] Batch disabled {len(disabled)} plugins")
        return disabled

    def bind_cognitive_functional(
        self,
        cognitive_plugin_id: str,
        functional_plugin_id: str,
        role: str = "primary",
        priority: int = 1,
        fallback_id: Optional[str] = None,
    ) -> None:
        """
        Bind a functional plugin to a cognitive plugin.
        
        Args:
            cognitive_plugin_id: The cognitive plugin
            functional_plugin_id: The functional plugin to bind
            role: Role of the functional plugin (e.g., 'primary', 'secondary')
            priority: Priority order
            fallback_id: Optional fallback plugin ID
            
        Example:
            >>> service.bind_cognitive_functional('q1_where_am_i', 'sensory_environment', role='primary')
        """
        # Verify both plugins exist
        cognitive = self._storage.get_plugin(cognitive_plugin_id)
        if not cognitive:
            raise KeyError(f"Cognitive plugin {cognitive_plugin_id} not found")
        
        functional = self._storage.get_plugin(functional_plugin_id)
        if not functional:
            raise KeyError(f"Functional plugin {functional_plugin_id} not found")
        
        # Create relation in database
        self._storage.create_relation(
            cognitive_plugin_id=cognitive_plugin_id,
            functional_plugin_id=functional_plugin_id,
            role=role,
            priority=priority,
            fallback_id=fallback_id,
        )
        
        logger.info(
            f"[Plugins] Bound {functional_plugin_id} to {cognitive_plugin_id} "
            f"(role={role}, priority={priority})"
        )

    def unbind_cognitive_functional(
        self,
        cognitive_plugin_id: str,
        functional_plugin_id: str,
    ) -> None:
        """
        Unbind a functional plugin from a cognitive plugin.
        
        Args:
            cognitive_plugin_id: The cognitive plugin
            functional_plugin_id: The functional plugin to unbind
            
        Example:
            >>> service.unbind_cognitive_functional('q1_where_am_i', 'sensory_environment')
        """
        # Delete from plugin_relations table
        self._storage.delete_relation(cognitive_plugin_id, functional_plugin_id)
        
        logger.info(
            f"[Plugins] Unbound {functional_plugin_id} from {cognitive_plugin_id}"
        )

    def _deactivate_conflicting_plugins(
        self,
        plugin_id: str,
        behavior_key: Optional[str],
        reason: str
    ) -> None:
        """
        Deactivate other plugins with the same behavior_key.
        
        Args:
            plugin_id: The plugin being activated
            behavior_key: The behavior key to check for conflicts
            reason: Reason for deactivation
        """
        if not behavior_key:
            return
        
        all_plugins = self._storage.list_plugins()
        for p in all_plugins:
            if (p["plugin_id"] != plugin_id and 
                p["behavior_key"] == behavior_key and 
                p["status"] == PluginLifecycleStatus.ACTIVE.value):
                try:
                    self.promote_plugin(
                        plugin_id=p["plugin_id"],
                        target_status=PluginLifecycleStatus.DEGRADED,
                        reason=f"Conflict with {plugin_id}: {reason}"
                    )
                except Exception as e:
                    logger.warning(f"[Plugins] Failed to deactivate conflicting plugin {p['plugin_id']}: {e}")

    def register_plugin(
        self,
        plugin_id: str,
        plugin_instance: Any,
        category: str,
        version: str = "1.0.0",
        behavior_key: Optional[str] = None,
    ) -> None:
        """
        Manually register a plugin instance.
        
        This is useful for dynamically registered plugins or external plugins.
        
        Args:
            plugin_id: Unique plugin identifier
            plugin_instance: The instantiated plugin object
            category: Plugin category ('cognitive', 'functional', etc.)
            version: Plugin version (default: 1.0.0)
            behavior_key: Optional behavior key for conflict detection
            
        Example:
            >>> service.register_plugin(
            ...     'custom_plugin',
            ...     my_plugin_instance,
            ...     category='functional',
            ...     version='2.0.0'
            ... )
        """
        spec_dict = {
            'plugin_id': plugin_id,
            'version': version,
            'status': PluginLifecycleStatus.CANDIDATE.value,
            'category': category,
            'behavior_key': behavior_key,
            'feature_code': getattr(plugin_instance, 'feature_code', plugin_id),
        }
        
        registration = {
            'source_kind': 'manual_registration',
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        
        self._storage.upsert_plugin(
            category=category,
            plugin_id=plugin_id,
            spec_dict=spec_dict,
            registration_dict=registration
        )
        
        self._plugin_instances[plugin_id] = plugin_instance
        self._plugin_specs[plugin_id] = spec_dict
        
        logger.info(f"[Plugins] Registered new plugin: {plugin_id}")
