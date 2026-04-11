from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.plugin_registry import AbstractPluginRegistry
from zentex.common.plugin_registry import PluginNotBoundError
from zentex.core.cognitive_tools_spec import CognitiveToolSpec, LogicalCognitiveToolSpec
from zentex.core.plugin_base import BasePluginSpec, PluginLifecycleStatus

logger = logging.getLogger(__name__)

RegisteredCognitiveSpec = CognitiveToolSpec | LogicalCognitiveToolSpec


class CognitiveToolRegistration(BaseModel):
    """
    Frozen runtime state wrapper for a registered cognitive tool.

    The object is immutable by design so state changes cannot silently happen
    outside the registry's audited update paths.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    spec: RegisteredCognitiveSpec
    internal_revision_id: int = Field(ge=1)
    source_kind: Literal["builtin", "user", "test_stub"] = "user"
    description: str = Field(min_length=1)
    usage_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    @property
    def plugin_id(self) -> str:
        return self.spec.plugin_id

    @property
    def status(self) -> PluginLifecycleStatus:
        return self.spec.status


class ForceEnableResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    registration: CognitiveToolRegistration
    auto_disabled_plugin_ids: List[str] = Field(default_factory=list)


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def append(self, event: Dict[str, Any]) -> None:
        self.events.append(event)


class CognitiveToolRegistry(AbstractPluginRegistry[BasePluginSpec]):
    """
    Audited runtime registry for cognitive tool plugins.

    Hard guarantees:
    - lifecycle changes go through the base plugin registry rules
    - runtime state is stored in immutable registration objects
    - every registration state mutation is written to transcript/audit output
    """

    AUTO_DEGRADE_FAILURE_THRESHOLD = 3

    def __init__(
        self,
        *,
        transcript_store: Optional[Any] = None,
        audit_logger: Optional[Any] = None,
        protected_plugin_ids: Set[str] | None = None,
        asset_store: Optional[Any] = None,
    ) -> None:
        if transcript_store is None and audit_logger is None:
            raise ValueError(
                "CognitiveToolRegistry requires transcript_store or audit_logger"
            )

        super().__init__(BasePluginSpec)
        self._transcript_store = transcript_store
        self._audit_logger = audit_logger
        self._asset_store = asset_store
        self._registrations: Dict[str, CognitiveToolRegistration] = {}
        self._protected_plugin_ids = set(protected_plugin_ids or set())
        self._is_test_sandbox = False
        self._next_internal_revision_id = 1
        
        # 🔄 BOOTSTRAP: Load existing cognitive plugins from the persistent store
        if self._asset_store:
            self._bootstrap_from_store()

    def _bootstrap_from_store(self) -> None:
        """Hydrate memory state from SQLite on startup."""
        if not self._asset_store or not hasattr(self._asset_store, "list_plugins"):
            return
            
        try:
            records = self._asset_store.list_plugins(category="cognitive")
            for r in records:
                # Reconstruct the registration from DB record
                # r["spec_json"] is already a dict if my asset_store does it, 
                # or a string if raw. AssetDatabaseStore.list_plugins should return dicts.
                spec_dict = r.get("spec_json")
                if not spec_dict:
                    continue
                if isinstance(spec_dict, str):
                    try:
                        spec_dict = json.loads(spec_dict)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "Failed to decode cognitive spec_json for %s: %s",
                            r.get("plugin_id"),
                            exc,
                        )
                        continue
                if not isinstance(spec_dict, dict):
                    logger.warning(
                        "Skipping cognitive spec for %s because spec_json is %s",
                        r.get("plugin_id"),
                        type(spec_dict).__name__,
                    )
                    continue
                spec_dict = self._sanitize_bootstrap_spec_dict(spec_dict)
                    
                # Dynamically determine the spec class (CognitiveToolSpec or LogicalCognitiveToolSpec)
                # For safety, we can use model_validate
                from zentex.core.cognitive_tools_spec import CognitiveToolSpec, LogicalCognitiveToolSpec
                
                spec = None
                validation_errors: list[str] = []
                for spec_cls in (LogicalCognitiveToolSpec, CognitiveToolSpec):
                    try:
                        spec = spec_cls.model_validate(spec_dict)
                        break
                    except Exception as exc:
                        validation_errors.append(f"{spec_cls.__name__}: {exc}")

                if spec is None:
                    logger.warning(
                        "Failed to validate cognitive spec for %s: %s",
                        r.get("plugin_id"),
                        " | ".join(validation_errors),
                    )
                    continue

                # Reconstruct registration
                reg = CognitiveToolRegistration(
                    spec=spec,
                    internal_revision_id=self._next_internal_revision_id,
                    source_kind=r.get("source_kind", "user"),
                    description=spec.purpose or r.get("plugin_id"),
                    usage_count=r.get("usage_count", 0),
                    failure_count=r.get("failure_count", 0),
                    created_at=datetime.fromisoformat(r["created_at"]) if isinstance(r.get("created_at"), str) else datetime.now(timezone.utc),
                    updated_at=datetime.fromisoformat(r["updated_at"]) if isinstance(r.get("updated_at"), str) else datetime.now(timezone.utc),
                    started_at=datetime.fromisoformat(r["started_at"]) if isinstance(r.get("started_at"), str) else None,
                    stopped_at=datetime.fromisoformat(r["stopped_at"]) if isinstance(r.get("stopped_at"), str) else None,
                )
                self._next_internal_revision_id += 1
                self._registrations[spec.plugin_id] = reg
                self._plugins[spec.plugin_id] = spec
                
            logger.info(f"Bootstrapped {len(self._registrations)} cognitive plugins from persistent store.")
        except Exception as exc:
            logger.error(f"Cognitive registry bootstrap failed: {exc}")

    @staticmethod
    def _sanitize_bootstrap_spec_dict(spec_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Drop legacy extra fields before strict pydantic validation."""
        allowed_keys = (
            set(CognitiveToolSpec.model_fields.keys())
            | set(LogicalCognitiveToolSpec.model_fields.keys())
        )
        return {key: value for key, value in spec_dict.items() if key in allowed_keys}


    @property
    def protected_plugin_ids(self) -> Set[str]:
        return set(self._protected_plugin_ids)

    def set_audit_sink(
        self,
        *,
        transcript_store: Any | None = None,
        audit_logger: Any | None = None,
    ) -> None:
        if transcript_store is None and audit_logger is None:
            raise ValueError("CognitiveToolRegistry audit sink cannot be empty")
        self._transcript_store = transcript_store
        self._audit_logger = audit_logger

    def register(
        self,
        plugin: RegisteredCognitiveSpec,
        *,
        source_kind: Literal["builtin", "user", "test_stub"] = "user",
        description: Optional[str] = None,
    ) -> Optional[CognitiveToolRegistration]:
        if source_kind == "test_stub" and not self._is_test_sandbox:
            raise PermissionError(
                "test_stub plugins must not be registered into the production registry"
            )
        try:
            runtime_plugin = plugin.__class__.model_validate(
                {
                    **plugin.model_dump(),
                    "status": PluginLifecycleStatus.CANDIDATE,
                }
            )
        except Exception:
            normalized = super().register(plugin)
            if normalized is None:
                return None
            runtime_plugin = normalized

        self._plugins[runtime_plugin.plugin_id] = runtime_plugin

        timestamp = datetime.now(timezone.utc)
        registration = CognitiveToolRegistration(
            spec=runtime_plugin,
            internal_revision_id=self._next_internal_revision_id,
            source_kind=source_kind,
            description=(description or runtime_plugin.purpose),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._next_internal_revision_id += 1
        self._registrations[runtime_plugin.plugin_id] = registration
        self._emit_audit_event(
            action="registered",
            plugin_id=runtime_plugin.plugin_id,
            old_state=None,
            new_state=self._serialize_registration(registration),
            audit_reason="registered_as_candidate",
        )
        return registration

    def get_registration(self, plugin_id: str) -> CognitiveToolRegistration:
        try:
            return self._registrations[plugin_id]
        except KeyError as exc:
            raise KeyError(f"Unknown cognitive tool: {plugin_id}") from exc

    def create_test_sandbox(self) -> "CognitiveToolRegistry":
        sandbox_sink = InMemoryAuditSink()
        sandbox = CognitiveToolRegistry(
            transcript_store=sandbox_sink,
            protected_plugin_ids=self._protected_plugin_ids,
        )
        sandbox._plugins = {
            plugin_id: plugin.model_copy(deep=True)
            for plugin_id, plugin in self._plugins.items()
        }
        sandbox._registrations = {
            plugin_id: registration.model_copy(deep=True)
            for plugin_id, registration in self._registrations.items()
        }
        sandbox._audit_records = list(self._audit_records)
        sandbox._is_test_sandbox = True
        return sandbox

    def resolve_bound_plugins(
        self,
        behavior_key: str,
        *,
        plugin_id: Optional[str] = None,
    ) -> List[CognitiveToolRegistration]:
        candidates = [
            registration
            for registration in self._registrations.values()
            if registration.spec.behavior_key == behavior_key
            and registration.status == PluginLifecycleStatus.ACTIVE
        ]
        if plugin_id is not None:
            candidates = [
                registration
                for registration in candidates
                if registration.plugin_id == plugin_id
            ]
        if not candidates:
            requested = plugin_id or behavior_key
            raise PluginNotBoundError(
                f"No active bound plugin is available for runtime use: {requested}"
            )
        return sorted(
            candidates,
            key=lambda registration: (
                self._version_key(registration.spec.version),
                registration.plugin_id,
            ),
            reverse=True,
        )

    def resolve_plugin_for_test(self, plugin_id: str) -> CognitiveToolRegistration:
        if not self._is_test_sandbox:
            raise PluginNotBoundError(
                "Inactive plugin resolution is only allowed inside an isolated test sandbox"
            )
        return self.get_registration(plugin_id)

    def promote_plugin(
        self,
        plugin_id: str,
        target_status: PluginLifecycleStatus,
        audit_reason: str,
    ) -> CognitiveToolRegistration:
        before = self.get_registration(plugin_id)
        if target_status == PluginLifecycleStatus.ACTIVE:
            self._deactivate_conflicting_active_plugins(plugin_id, audit_reason)
        promoted_spec = super().promote_plugin(plugin_id, target_status, audit_reason)
        timestamp = datetime.now(timezone.utc)
        update_payload: Dict[str, Any] = {
            "spec": promoted_spec,
            "updated_at": timestamp,
        }
        if target_status == PluginLifecycleStatus.ACTIVE:
            update_payload["started_at"] = timestamp
            update_payload["stopped_at"] = None
        elif target_status == PluginLifecycleStatus.REVOKED:
            update_payload["stopped_at"] = timestamp
        updated = before.model_copy(update=update_payload)
        self._registrations[plugin_id] = updated
        self._emit_audit_event(
            action="promoted",
            plugin_id=plugin_id,
            old_state=self._serialize_registration(before),
            new_state=self._serialize_registration(updated),
            audit_reason=audit_reason,
        )
        return updated

    def revoke_plugin(self, plugin_id: str, reason: str) -> CognitiveToolRegistration:
        before = self.get_registration(plugin_id)
        revoked_spec = super().revoke_plugin(plugin_id, reason)
        timestamp = datetime.now(timezone.utc)
        updated = before.model_copy(
            update={
                "spec": revoked_spec,
                "updated_at": timestamp,
                "stopped_at": timestamp,
            }
        )
        self._registrations[plugin_id] = updated
        self._emit_audit_event(
            action="revoked",
            plugin_id=plugin_id,
            old_state=self._serialize_registration(before),
            new_state=self._serialize_registration(updated),
            audit_reason=reason,
        )
        return updated

    def record_tool_usage(
        self, plugin_id: str, *, used_at: Optional[datetime] = None
    ) -> CognitiveToolRegistration:
        before = self.get_registration(plugin_id)
        if not self._is_test_sandbox and before.status != PluginLifecycleStatus.ACTIVE:
            raise PluginNotBoundError(
                f"Cannot record runtime usage for a plugin that is not active: {plugin_id}"
            )
        timestamp = used_at or datetime.now(timezone.utc)
        updated = before.model_copy(
            update={
                "usage_count": before.usage_count + 1,
                "updated_at": timestamp,
                "last_used_at": timestamp,
                "failure_count": 0,
            }
        )
        self._registrations[plugin_id] = updated
        return updated

    def record_tool_failure(
        self, plugin_id: str, error_msg: str
    ) -> CognitiveToolRegistration:
        before = self.get_registration(plugin_id)
        if not self._is_test_sandbox and before.status != PluginLifecycleStatus.ACTIVE:
            raise PluginNotBoundError(
                f"Cannot record runtime failure for a plugin that is not active: {plugin_id}"
            )
        timestamp = datetime.now(timezone.utc)
        failure_updated = before.model_copy(
            update={
                "failure_count": before.failure_count + 1,
                "updated_at": timestamp,
            }
        )
        self._registrations[plugin_id] = failure_updated
        self._emit_audit_event(
            action="failure_recorded",
            plugin_id=plugin_id,
            old_state=self._serialize_registration(before),
            new_state=self._serialize_registration(failure_updated),
            audit_reason=error_msg,
            error_msg=error_msg,
        )

        if (
            failure_updated.failure_count >= self.AUTO_DEGRADE_FAILURE_THRESHOLD
            and failure_updated.status != PluginLifecycleStatus.DEGRADED
            and failure_updated.status != PluginLifecycleStatus.REVOKED
        ):
            degraded = self.promote_plugin(
                plugin_id,
                PluginLifecycleStatus.DEGRADED,
                audit_reason=f"auto_degraded_after_failures: {error_msg}",
            )
            return degraded

        return failure_updated

    def list_registrations(self) -> List[CognitiveToolRegistration]:
        return list(self._registrations.values())

    def can_force_disable_plugin(self, plugin_id: str) -> bool:
        registration = self.get_registration(plugin_id)
        if registration.status != PluginLifecycleStatus.ACTIVE:
            return False
        return self._resolve_disable_replacement(registration) is not None

    def force_enable_plugin(
        self,
        plugin_id: str,
        *,
        audit_reason: str,
    ) -> ForceEnableResult:
        before = self.get_registration(plugin_id)
        if not before.spec.is_official_release:
            raise PermissionError(
                f"Only official-release plugins can be force-enabled: {plugin_id}"
            )
        auto_disabled_plugin_ids = self._deactivate_conflicting_active_plugins(
            plugin_id, audit_reason
        )
        timestamp = datetime.now(timezone.utc)
        forced_spec = before.spec.model_copy(
            update={"status": PluginLifecycleStatus.ACTIVE}
        )
        self._plugins[plugin_id] = forced_spec
        updated = before.model_copy(
            update={
                "spec": forced_spec,
                "updated_at": timestamp,
                "started_at": timestamp,
                "stopped_at": None,
            }
        )
        self._registrations[plugin_id] = updated
        self._emit_audit_event(
            action="force_enabled",
            plugin_id=plugin_id,
            old_state=self._serialize_registration(before),
            new_state=self._serialize_registration(updated),
            audit_reason=audit_reason,
        )
        return ForceEnableResult(
            registration=updated,
            auto_disabled_plugin_ids=auto_disabled_plugin_ids,
        )

    def force_disable_plugin(
        self,
        plugin_id: str,
        *,
        audit_reason: str,
    ) -> CognitiveToolRegistration:
        before = self.get_registration(plugin_id)
        if before.status != PluginLifecycleStatus.ACTIVE:
            raise ValueError(f"Plugin is not active: {plugin_id}")
        if self._resolve_disable_replacement(before) is None:
            raise ValueError(
                f"Plugin cannot be force-disabled safely because no fallback is available: {plugin_id}"
            )

        timestamp = datetime.now(timezone.utc)
        disabled_spec = before.spec.transition_to(
            PluginLifecycleStatus.DEGRADED,
            revocation_reasons=[audit_reason],
        )
        self._plugins[plugin_id] = disabled_spec
        updated = before.model_copy(
            update={
                "spec": disabled_spec,
                "updated_at": timestamp,
                "stopped_at": timestamp,
            }
        )
        self._registrations[plugin_id] = updated
        self._emit_audit_event(
            action="force_disabled",
            plugin_id=plugin_id,
            old_state=self._serialize_registration(before),
            new_state=self._serialize_registration(updated),
            audit_reason=audit_reason,
        )

        replacement = self._activate_fallback_for_behavior(updated, audit_reason)
        return replacement or updated

    def delete_plugin(
        self,
        plugin_id: str,
        *,
        audit_reason: str,
    ) -> None:
        before = self.get_registration(plugin_id)
        if plugin_id in self._protected_plugin_ids:
            raise PermissionError(f"Protected default plugin cannot be deleted: {plugin_id}")
        if before.status == PluginLifecycleStatus.ACTIVE:
            raise ValueError(f"Active plugin cannot be deleted: {plugin_id}")

        self._registrations.pop(plugin_id, None)
        self._plugins.pop(plugin_id, None)
        self._emit_audit_event(
            action="deleted",
            plugin_id=plugin_id,
            old_state=self._serialize_registration(before),
            new_state=None,
            audit_reason=audit_reason,
        )

    def _deactivate_conflicting_active_plugins(
        self,
        plugin_id: str,
        audit_reason: str,
    ) -> List[str]:
        target = self.get_registration(plugin_id)
        if target.spec.supports_multiple_plugins:
            return []

        auto_disabled_plugin_ids: List[str] = []
        for registration in list(self._registrations.values()):
            if registration.plugin_id == plugin_id:
                continue
            if registration.spec.behavior_key != target.spec.behavior_key:
                continue
            if registration.status != PluginLifecycleStatus.ACTIVE:
                continue
            timestamp = datetime.now(timezone.utc)
            degraded_spec = registration.spec.transition_to(
                PluginLifecycleStatus.DEGRADED,
                revocation_reasons=[f"conflict_with_{plugin_id}"],
            )
            self._plugins[registration.plugin_id] = degraded_spec
            updated = registration.model_copy(
                update={
                    "spec": degraded_spec,
                    "updated_at": timestamp,
                    "stopped_at": timestamp,
                }
            )
            self._registrations[registration.plugin_id] = updated
            auto_disabled_plugin_ids.append(registration.plugin_id)
            self._emit_audit_event(
                action="auto_deactivated_conflict",
                plugin_id=registration.plugin_id,
                old_state=self._serialize_registration(registration),
                new_state=self._serialize_registration(updated),
                audit_reason=f"{audit_reason}: conflict_on_behavior_key",
            )
        return auto_disabled_plugin_ids

    def _activate_fallback_for_behavior(
        self,
        disabled: CognitiveToolRegistration,
        audit_reason: str,
    ) -> Optional[CognitiveToolRegistration]:
        replacement = self._resolve_disable_replacement(disabled)
        if replacement is None:
            return None
        if replacement.plugin_id == disabled.plugin_id:
            return None
        return self.force_enable_plugin(
            replacement.plugin_id,
            audit_reason=f"{audit_reason}: fallback_activated",
        ).registration

    def _resolve_disable_replacement(
        self,
        disabled: CognitiveToolRegistration,
    ) -> Optional[CognitiveToolRegistration]:
        behavior_key = disabled.spec.behavior_key
        behavior_registrations = [
            registration
            for registration in self._registrations.values()
            if registration.spec.behavior_key == behavior_key
        ]
        active_others = [
            registration
            for registration in behavior_registrations
            if registration.plugin_id != disabled.plugin_id
            and registration.status == PluginLifecycleStatus.ACTIVE
        ]

        if disabled.spec.supports_multiple_plugins and active_others:
            return active_others[0]
        if not disabled.spec.supports_multiple_plugins and active_others:
            return active_others[0]

        return self._select_fallback_candidate(disabled, behavior_registrations)

    def _select_fallback_candidate(
        self,
        disabled: CognitiveToolRegistration,
        behavior_registrations: List[CognitiveToolRegistration],
    ) -> Optional[CognitiveToolRegistration]:
        previous_official_candidates = [
            registration
            for registration in behavior_registrations
            if registration.plugin_id != disabled.plugin_id
            and registration.spec.is_official_release
            and registration.status != PluginLifecycleStatus.REVOKED
            and self._version_key(registration.spec.version)
            < self._version_key(disabled.spec.version)
        ]
        if previous_official_candidates:
            return max(
                previous_official_candidates,
                key=lambda registration: self._version_key(registration.spec.version),
            )

        official_candidates = [
            registration
            for registration in behavior_registrations
            if registration.plugin_id != disabled.plugin_id
            and registration.spec.is_official_release
            and registration.status != PluginLifecycleStatus.REVOKED
        ]
        if official_candidates:
            return max(
                official_candidates,
                key=lambda registration: self._version_key(registration.spec.version),
            )

        default_candidates = [
            registration
            for registration in behavior_registrations
            if registration.plugin_id != disabled.plugin_id
            and registration.spec.is_default_version
            and registration.status != PluginLifecycleStatus.REVOKED
        ]
        if default_candidates:
            return max(
                default_candidates,
                key=lambda registration: self._version_key(registration.spec.version),
            )

        return None

    def _version_key(self, version: str) -> Tuple[int, ...]:
        parts: List[int] = []
        for chunk in version.split("."):
            try:
                parts.append(int(chunk))
            except ValueError:
                parts.append(0)
        return tuple(parts)
    def _emit_audit_event(
        self,
        *,
        action: Literal["registered", "promoted", "revoked", "deleted"],
        plugin_id: str,
        audit_reason: str,
        old_state: Optional[Dict[str, Any]] = None,
        new_state: Optional[Dict[str, Any]] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        # 🔄 DB SYNC: Perform real-time synchronization of cognitive plugin state
        if self._asset_store and hasattr(self._asset_store, "upsert_plugin") and not self._is_test_sandbox:
            if action == "deleted":
                if hasattr(self._asset_store, "delete_plugin"):
                    self._asset_store.delete_plugin(plugin_id)
            elif new_state:
                # We need the original spec to serialize correctly
                reg = self._registrations.get(plugin_id)
                if reg:
                    self._asset_store.upsert_plugin(
                        category="cognitive",
                        plugin_id=plugin_id,
                        spec_dict=reg.spec.model_dump(mode="json"),
                        registration_dict=new_state
                    )

        event = {
            "event_type": "cognitive_tool_registry_state_changed",
            "plugin_id": plugin_id,
            "action": action,
            "audit_reason": audit_reason,
            "old_state": old_state,
            "new_state": new_state,
            "error_msg": error_msg,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._transcript_store is not None:
            append = getattr(self._transcript_store, "append", None)
            if append is None:
                raise TypeError("transcript_store must expose an append method")
            append(event)
            return

        if self._audit_logger is None:
            raise RuntimeError("Audit sink disappeared during registry update")

        append = getattr(self._audit_logger, "append", None)
        if callable(append):
            append(event)
            return

        info = getattr(self._audit_logger, "info", None)
        if callable(info):
            info("cognitive_tool_registry_state_changed", extra=event)
            return

        raise TypeError("audit_logger must expose append or info")

    def _serialize_registration(
        self, registration: CognitiveToolRegistration
    ) -> Dict[str, Any]:
        return {
            "plugin_id": registration.spec.plugin_id,
            "internal_revision_id": registration.internal_revision_id,
            "source_kind": registration.source_kind,
            "description": registration.description,
            "status": registration.spec.status.value,
            "usage_count": registration.usage_count,
            "failure_count": registration.failure_count,
            "created_at": registration.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": registration.updated_at.astimezone(timezone.utc).isoformat(),
            "started_at": (
                registration.started_at.astimezone(timezone.utc).isoformat()
                if registration.started_at is not None
                else None
            ),
            "stopped_at": (
                registration.stopped_at.astimezone(timezone.utc).isoformat()
                if registration.stopped_at is not None
                else None
            ),
            "last_used_at": (
                registration.last_used_at.astimezone(timezone.utc).isoformat()
                if registration.last_used_at is not None
                else None
            ),
            "version": registration.spec.version,
        }
