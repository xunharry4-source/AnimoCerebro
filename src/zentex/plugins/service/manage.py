from __future__ import annotations
"""
Management Service: Plugin Lifecycle and Relationship Management

Handles:
- Plugin promotion (status transitions)
- Plugin registration (manual)
- Enabling/disabling plugins
- Managing plugin relationships
- Conflict detection and resolution
"""


import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from zentex.plugins.models import PluginLifecycleStatus
from zentex.common.plugin_ids import (
    NINE_QUESTION_Q1,
    NINE_QUESTION_Q2,
    NINE_QUESTION_Q3,
    NINE_QUESTION_Q4,
    NINE_QUESTION_Q5,
    NINE_QUESTION_Q6,
    NINE_QUESTION_Q7,
    NINE_QUESTION_Q8,
    NINE_QUESTION_Q9,
    MEMORY_EXTRACTOR,
    REFLECTION_GENERATOR,
)
from zentex.plugins.plugin_ids import canonicalize_plugin_id

logger = logging.getLogger(__name__)


# Plugin IDs that must always remain ACTIVE and can never be disabled or
# revoked.  These are the core cognitive operators that the runtime depends on
# for every inference cycle.  Even during upgrades at least one instance must
# remain active.
_ALWAYS_ACTIVE_PLUGIN_IDS: frozenset[str] = frozenset({
    NINE_QUESTION_Q1,
    NINE_QUESTION_Q2,
    NINE_QUESTION_Q3,
    NINE_QUESTION_Q4,
    NINE_QUESTION_Q5,
    NINE_QUESTION_Q6,
    NINE_QUESTION_Q7,
    NINE_QUESTION_Q8,
    NINE_QUESTION_Q9,
    MEMORY_EXTRACTOR,
    REFLECTION_GENERATOR,
})


def _is_always_active(plugin_id: str) -> bool:
    """Return True for plugins that must never be deactivated."""
    return (
        plugin_id in _ALWAYS_ACTIVE_PLUGIN_IDS
        or plugin_id.startswith("nine-question-")
        or plugin_id.startswith("nine_question_")
    )


def _is_cognitive_category(plugin: Optional[Dict[str, Any]]) -> bool:
    return str((plugin or {}).get("category") or "").strip().lower() == "cognitive"


def _get_lifecycle_status(plugin: Optional[Dict[str, Any]]) -> str:
    return str((plugin or {}).get("lifecycle_status") or "").strip().lower()


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
    
    def __init__(self, storage, plugin_instances, plugin_specs, get_factories_fn, determine_category_fn, index_fn=None):
        """
        Initialize management service.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            plugin_specs: Plugin spec cache
            get_factories_fn: Function to get plugin factories
            determine_category_fn: Function to determine plugin category
            index_fn: Optional function to index plugin runtime state
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._plugin_specs = plugin_specs
        self._get_factories = get_factories_fn
        self._determine_category = determine_category_fn
        self._index_fn = index_fn

    def _sync_instance_status(self, plugin_id: str, lifecycle_status: PluginLifecycleStatus) -> None:
        plugin = self._plugin_instances.get(plugin_id)
        if plugin is None:
            return
        try:
            updated_plugin = plugin.model_copy(update={"lifecycle_status": lifecycle_status})
            self._plugin_instances[plugin_id] = updated_plugin
        except Exception:
            logger.debug("[Plugins] Could not sync runtime instance status for %s", plugin_id)

    def _ensure_runtime_instance_loaded(self, plugin_id: str) -> bool:
        """Instantiate an ACTIVE plugin into memory when startup reused persisted DB rows."""
        if plugin_id in self._plugin_instances:
            return True

        factory = self._get_factories().get(plugin_id)
        if not factory:
            logger.error(
                "[Plugins] Cannot load runtime instance for %s: factory not found.",
                plugin_id,
            )
            return False

        try:
            instance = factory()
            if self._index_fn is not None:
                self._index_fn(plugin_id, instance=instance)
            else:
                self._plugin_instances[plugin_id] = instance
            logger.info("[Plugins] Rehydrated runtime instance for ACTIVE plugin %s", plugin_id)
            return True
        except Exception as exc:
            logger.error(
                "[Plugins] Failed to rehydrate runtime instance for ACTIVE plugin %s: %s",
                plugin_id,
                exc,
                exc_info=True,
            )
            return False

    def promote_plugin(
        self,
        plugin_id: str,
        target_lifecycle_status: PluginLifecycleStatus,
        reason: str,
    ) -> None:
        """Promote a plugin to a new lifecycle state.

        State transitions:
            CANDIDATE → SANDBOX_VERIFIED → ACTIVE ↔ DEGRADED → REVOKED

        Blue-green activation policy
        ----------------------------
        When promoting to ACTIVE the method follows a strict blue-green order
        so that the currently running version is **never stopped before the new
        version is confirmed to be working**:

        1. Locate currently active plugins that share the same ``behavior_key``
           (the "old" versions).
        2. Try to instantiate the new plugin.  If instantiation fails:
           - Log the error.
           - Leave the DB and the old version completely untouched.
           - Return without raising (caller can inspect logs).
        3. Only after the new instance is confirmed healthy:
           - Write the ACTIVE status to the DB.
           - Stop (DEGRADED) the previously active versions.

        This applies to both cognitive and functional plugins.  For cognitive
        plugins the policy is additionally reinforced by the always-active guard
        that prevents any deactivation call from reaching them directly.

        Args:
            plugin_id: Plugin to promote.
            target_lifecycle_status: Target lifecycle status.
            reason: Human-readable reason (written to audit log).

        Raises:
            KeyError: If ``plugin_id`` is not registered in the database.
        """
        plugin = self._storage.get_plugin(plugin_id)
        if not plugin:
            raise KeyError(f"Plugin {plugin_id} not found in database.")

        # ── Always-active guard ───────────────────────────────────────────
        # Core cognitive plugins must never be degraded or revoked.
        if (_is_always_active(plugin_id) or _is_cognitive_category(plugin)) and target_lifecycle_status not in {
            PluginLifecycleStatus.ACTIVE,
            PluginLifecycleStatus.SANDBOX_VERIFIED,
        }:
            message = (
                f"Cognitive plugin {plugin_id} cannot transition to {target_lifecycle_status.value}; "
                "cognitive plugins must always keep at least one active version."
            )
            logger.warning("[Plugins] %s", message)
            raise ValueError(message)

        # ── Blue-green promotion to ACTIVE ────────────────────────────────
        if target_lifecycle_status == PluginLifecycleStatus.ACTIVE:
            # Step 1: snapshot the currently active conflicts BEFORE touching anything.
            conflicts = self._find_active_conflicts(plugin_id, plugin.get("behavior_key"))

            # Step 2: ensure the new plugin instance is ready.
            if plugin_id not in self._plugin_instances:
                factory = self._get_factories().get(plugin_id)
                if not factory:
                    raise ValueError(
                        f"Activation of {plugin_id} aborted — plugin implementation does not exist."
                    )
                try:
                    self._plugin_instances[plugin_id] = factory()
                except Exception as exc:
                    if conflicts:
                        active_info = (
                            f"Currently active version(s) [{', '.join(conflicts)}] will remain running."
                        )
                    else:
                        active_info = "No currently active version to fall back to."
                    message = (
                        f"Activation of {plugin_id} aborted — instantiation failed. "
                        f"{active_info} Error: {exc}"
                    )
                    logger.error(
                        "[Plugins] Activation of %s aborted — instantiation failed. "
                        "%s  Error: %s",
                        plugin_id,
                        active_info,
                        exc,
                    )
                    # If this is a cognitive plugin and there are no fallbacks, escalate.
                    if not conflicts and _is_always_active(plugin_id):
                        logger.critical(
                            "[Plugins] CRITICAL — Cognitive plugin %s failed to activate "
                            "and NO fallback version is currently ACTIVE. "
                            "The cognitive capability '%s' is OFFLINE. "
                            "Activation error: %s. "
                            "ACTION REQUIRED: investigate why the plugin cannot be instantiated "
                            "and restore an active version immediately.",
                            plugin_id,
                            plugin.get("behavior_key", plugin_id),
                            exc,
                        )
                    # Abort: DB and old versions are untouched.
                    raise ValueError(message) from exc

            # Step 3: new instance is healthy — commit the new status to DB.
            now = datetime.now(timezone.utc).isoformat()
            spec_dict = json.loads(plugin["spec_json"])
            spec_dict["lifecycle_status"] = PluginLifecycleStatus.ACTIVE.value
            spec_dict["operational_status"] = "enabled"
            self._storage.upsert_plugin(
                category=plugin["category"],
                plugin_id=plugin_id,
                spec_dict=spec_dict,
                registration_dict={
                    **plugin,
                    "lifecycle_status": PluginLifecycleStatus.ACTIVE.value,
                    "operational_status": "enabled",
                    "updated_at": now,
                    "started_at": now,
                    "stopped_at": None,
                },
            )
            if self._index_fn:
                self._index_fn(
                    plugin_id,
                    instance=self._plugin_instances.get(plugin_id),
                    spec_dict=spec_dict,
                )
            else:
                self._plugin_specs[plugin_id] = spec_dict
            self._sync_instance_status(plugin_id, PluginLifecycleStatus.ACTIVE)
            logger.info("[Plugins] %s activated. Reason: %s", plugin_id, reason)

            # Step 4: now it is safe to stop the old versions.
            for conflict_id in conflicts:
                try:
                    self._stop_superseded_plugin(conflict_id, superseded_by=plugin_id, reason=reason)
                except Exception as exc:
                    logger.warning(
                        "[Plugins] Could not stop superseded plugin %s after activating %s: %s",
                        conflict_id,
                        plugin_id,
                        exc,
                    )
            return

        # ── All other status transitions (non-ACTIVE) ─────────────────────
        now = datetime.now(timezone.utc).isoformat()
        spec_dict = json.loads(plugin["spec_json"])
        spec_dict["lifecycle_status"] = target_lifecycle_status.value

        registration_update: dict[str, Any] = {
            "lifecycle_status": target_lifecycle_status.value,
            "operational_status": "unavailable",
            "updated_at": now,
        }
        if target_lifecycle_status in {PluginLifecycleStatus.REVOKED, PluginLifecycleStatus.DEGRADED}:
            registration_update["stopped_at"] = now

        self._storage.upsert_plugin(
            category=plugin["category"],
            plugin_id=plugin_id,
            spec_dict=spec_dict,
            registration_dict={**plugin, **registration_update},
        )
        self._plugin_specs[plugin_id] = spec_dict
        self._sync_instance_status(plugin_id, target_lifecycle_status)
        logger.info("[Plugins] %s → %s. Reason: %s", plugin_id, target_lifecycle_status.value, reason)

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
        plugin = self._storage.get_plugin(plugin_id)
        if _is_always_active(plugin_id) or _is_cognitive_category(plugin):
            message = (
                f"Cognitive plugin {plugin_id} cannot be disabled; "
                "cognitive plugins must remain active."
            )
            logger.warning("[Plugins] %s Reason: %s", message, reason)
            raise ValueError(message)
        self.promote_plugin(plugin_id, PluginLifecycleStatus.DEGRADED, reason)

    def _log_missing_active_cognitive_behaviors(self) -> None:
        by_behavior: Dict[str, List[Dict[str, Any]]] = {}
        for plugin in self._storage.list_plugins(category="cognitive"):
            behavior_key = str(plugin.get("behavior_key") or plugin["plugin_id"])
            by_behavior.setdefault(behavior_key, []).append(plugin)

        for behavior_key, plugins in by_behavior.items():
            active_versions = [
                plugin["plugin_id"]
                for plugin in plugins
                if _get_lifecycle_status(plugin) == PluginLifecycleStatus.ACTIVE.value
            ]
            if active_versions:
                continue

            plugin_ids = [plugin["plugin_id"] for plugin in plugins]
            failure_reasons = [
                f"{plugin['plugin_id']}:{_get_lifecycle_status(plugin) or 'unknown'}"
                for plugin in plugins
            ]
            logger.critical(
                "[Plugins] CRITICAL — cognitive behavior '%s' has NO active version. "
                "Affected plugins=%s. Current states=%s. "
                "This functionality is unavailable until one version activates successfully.",
                behavior_key,
                plugin_ids,
                failure_reasons,
            )

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
            
            if should_disable and _get_lifecycle_status(plugin) == PluginLifecycleStatus.ACTIVE.value:
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
                _get_lifecycle_status(p) == PluginLifecycleStatus.ACTIVE.value):
                if _is_always_active(p["plugin_id"]):
                    logger.warning(
                        "[Plugins] Skipping conflict-deactivation of %s: core cognitive plugins must stay ACTIVE.",
                        p["plugin_id"],
                    )
                    continue
                try:
                    self.promote_plugin(
                        plugin_id=p["plugin_id"],
                        target_lifecycle_status=PluginLifecycleStatus.DEGRADED,
                        reason=f"Conflict with {plugin_id}: {reason}"
                    )
                except Exception as e:
                    logger.warning(f"[Plugins] Failed to deactivate conflicting plugin {p['plugin_id']}: {e}")

    def _find_active_conflicts(
        self,
        plugin_id: str,
        behavior_key: Optional[str],
    ) -> List[str]:
        """Return IDs of currently ACTIVE plugins that share the same behavior_key.

        The activating plugin itself is excluded from the result.  If
        ``behavior_key`` is None or empty an empty list is returned because
        there is no meaningful conflict to detect.
        """
        if not behavior_key:
            return []
        conflicts: List[str] = []
        target_canonical = canonicalize_plugin_id(plugin_id)
        for p in self._storage.list_plugins():
            pid = p["plugin_id"]
            if (
                canonicalize_plugin_id(pid) != target_canonical
                and p.get("behavior_key") == behavior_key
                and _get_lifecycle_status(p) == PluginLifecycleStatus.ACTIVE.value
            ):
                conflicts.append(pid)
        return conflicts

    def _stop_superseded_plugin(
        self,
        plugin_id: str,
        *,
        superseded_by: str,
        reason: str,
    ) -> None:
        """Degrade a plugin that has been superseded by a newly activated version.

        Always-active cognitive plugins are protected: if the superseded plugin
        is in the always-active set the call is silently skipped (the blue-green
        guard at ``promote_plugin`` level ensures this should never be needed for
        cognitive plugins, but the check here provides defense-in-depth).

        After degrading, the method checks whether the superseded plugin is
        cognitive and whether ANY version of the same behavior_key remains ACTIVE.
        If no active version survives the warning is escalated to CRITICAL level
        so that operators are immediately alerted.
        """
        # Always-active guard: cognitive plugins can never be stopped by the
        # blue-green supersession flow.  They must remain running until an operator
        # explicitly upgrades them through the dedicated upgrade path.
        if _is_always_active(plugin_id):
            logger.warning(
                "[Plugins] Refusing to stop always-active cognitive plugin %s "
                "(superseded_by=%s): cognitive plugins must keep at least one active version.",
                plugin_id,
                superseded_by,
            )
            return

        # Transition to DEGRADED (not REVOKED — keeps audit trail, allows rollback).
        now = datetime.now(timezone.utc).isoformat()
        plugin = self._storage.get_plugin(plugin_id)
        if plugin is None:
            logger.warning(
                "[Plugins] _stop_superseded_plugin: plugin %s not found in DB, skipping.",
                plugin_id,
            )
            return

        spec_dict = json.loads(plugin["spec_json"])
        spec_dict["lifecycle_status"] = PluginLifecycleStatus.DEGRADED.value
        self._storage.upsert_plugin(
            category=plugin["category"],
            plugin_id=plugin_id,
            spec_dict=spec_dict,
            registration_dict={
                **plugin,
                "lifecycle_status": PluginLifecycleStatus.DEGRADED.value,
                "operational_status": "unavailable",
                "updated_at": now,
                "stopped_at": now,
            },
        )
        self._plugin_specs[plugin_id] = spec_dict
        self._sync_instance_status(plugin_id, PluginLifecycleStatus.DEGRADED)
        logger.info(
            "[Plugins] Superseded plugin %s → DEGRADED (replaced by %s). Reason: %s",
            plugin_id,
            superseded_by,
            reason,
        )

        # ── Cognitive zero-survivor check ────────────────────────────────────
        # After stopping this plugin, verify that at least one ACTIVE version of
        # the same behavior_key still exists.  If none survive, the cognitive
        # capability is completely offline — emit a CRITICAL warning.
        behavior_key = plugin.get("behavior_key")
        if behavior_key:
            survivors = [
                p["plugin_id"]
                for p in self._storage.list_plugins()
                if p.get("behavior_key") == behavior_key
                and _get_lifecycle_status(p) == PluginLifecycleStatus.ACTIVE.value
            ]
            if not survivors:
                logger.critical(
                    "[Plugins] CRITICAL — NO ACTIVE VERSION REMAINING for behavior_key '%s' "
                    "after stopping %s (superseded by %s). "
                    "The cognitive capability provided by this behavior_key is now OFFLINE. "
                    "Reason that triggered this stop: %s. "
                    "Affected plugin that could not be started: %s. "
                    "ACTION REQUIRED: manually re-activate a plugin with behavior_key '%s' "
                    "or the associated cognitive question will fail every inference cycle.",
                    behavior_key,
                    plugin_id,
                    superseded_by,
                    reason,
                    superseded_by,
                    behavior_key,
                )

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
            'lifecycle_status': PluginLifecycleStatus.CANDIDATE.value,
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

    def activate_all_functional(
        self,
        reason: str = "Bulk functional plugin activation",
    ) -> Dict[str, Any]:
        """Activate all registered functional plugins that are not yet ACTIVE.

        Cognitive plugins are skipped — they are managed separately and must
        never be started or stopped in bulk.

        Each plugin is promoted through SANDBOX_VERIFIED → ACTIVE following the
        blue-green policy implemented in ``promote_plugin``.  Failures for
        individual plugins are logged and collected but do not abort the batch.

        Args:
            reason: Human-readable reason written to the audit log for each activation.

        Returns:
            A summary dict::

                {
                    "activated": ["plugin-a", "plugin-b"],   # newly activated
                    "already_active": ["plugin-c"],           # were already ACTIVE
                    "skipped_cognitive": ["nine-question-q1-..."],
                    "failed": {"plugin-d": "error message"},  # activation errors
                }
        """
        all_plugins = self._storage.list_plugins()

        result: Dict[str, Any] = {
            "activated": [],
            "already_active": [],
            "skipped_cognitive": [],
            "failed": {},
        }

        for p in all_plugins:
            pid = p["plugin_id"]

            # Never touch cognitive plugins in a bulk activation sweep.
            if p.get("category") == "cognitive" or _is_always_active(pid):
                result["skipped_cognitive"].append(pid)
                continue

            current_status = _get_lifecycle_status(p)
            if current_status == PluginLifecycleStatus.ACTIVE.value:
                if self._ensure_runtime_instance_loaded(pid):
                    result["already_active"].append(pid)
                else:
                    result["failed"][pid] = "active plugin could not be rehydrated into memory"
                continue

            # Promote through sandbox → active.
            try:
                if current_status != PluginLifecycleStatus.SANDBOX_VERIFIED.value:
                    self.promote_plugin(
                        pid,
                        PluginLifecycleStatus.SANDBOX_VERIFIED,
                        reason=f"[activate_all_functional] pre-activation sandbox pass — {reason}",
                    )
                self.promote_plugin(
                    pid,
                    PluginLifecycleStatus.ACTIVE,
                    reason=reason,
                )
                # Confirm it actually reached ACTIVE (promote_plugin can silently
                # abort on instantiation failure).
                refreshed = self._storage.get_plugin(pid)
                if refreshed and _get_lifecycle_status(refreshed) == PluginLifecycleStatus.ACTIVE.value:
                    result["activated"].append(pid)
                else:
                    result["failed"][pid] = "promote_plugin returned without error but plugin is not ACTIVE"
            except Exception as exc:
                result["failed"][pid] = str(exc)
                logger.error("[Plugins] activate_all_functional: failed to activate %s — %s", pid, exc)

        logger.info(
            "[Plugins] activate_all_functional complete — activated=%d, already_active=%d, "
            "skipped_cognitive=%d, failed=%d",
            len(result["activated"]),
            len(result["already_active"]),
            len(result["skipped_cognitive"]),
            len(result["failed"]),
        )
        if result["failed"]:
            logger.warning(
                "[Plugins] activate_all_functional: %d plugin(s) could not be activated: %s",
                len(result["failed"]),
                list(result["failed"].keys()),
            )
        return result

    def activate_all_cognitive(
        self,
        reason: str = "Bulk cognitive plugin activation",
    ) -> Dict[str, Any]:
        """Activate all registered cognitive plugins while preserving blue-green semantics."""
        all_plugins = self._storage.list_plugins()

        result: Dict[str, Any] = {
            "activated": [],
            "already_active": [],
            "failed": {},
        }

        for plugin in all_plugins:
            pid = plugin["plugin_id"]
            if plugin.get("category") != "cognitive":
                continue

            current_status = _get_lifecycle_status(plugin)
            if current_status == PluginLifecycleStatus.ACTIVE.value:
                if self._ensure_runtime_instance_loaded(pid):
                    result["already_active"].append(pid)
                else:
                    result["failed"][pid] = "active plugin could not be rehydrated into memory"
                continue

            try:
                if current_status != PluginLifecycleStatus.SANDBOX_VERIFIED.value:
                    self.promote_plugin(
                        pid,
                        PluginLifecycleStatus.SANDBOX_VERIFIED,
                        reason=f"[activate_all_cognitive] pre-activation sandbox pass — {reason}",
                    )
                self.promote_plugin(pid, PluginLifecycleStatus.ACTIVE, reason=reason)
                refreshed = self._storage.get_plugin(pid)
                if refreshed and _get_lifecycle_status(refreshed) == PluginLifecycleStatus.ACTIVE.value:
                    result["activated"].append(pid)
                else:
                    result["failed"][pid] = "promote_plugin returned without error but plugin is not ACTIVE"
            except Exception as exc:
                result["failed"][pid] = str(exc)
                logger.error("[Plugins] activate_all_cognitive: failed to activate %s — %s", pid, exc)

        if result["failed"]:
            logger.error(
                "[Plugins] activate_all_cognitive: failed cognitive plugins=%s",
                result["failed"],
            )
        self._log_missing_active_cognitive_behaviors()
        return result
