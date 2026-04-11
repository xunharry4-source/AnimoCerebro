from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zentex.common.plugin_registry import AbstractPluginRegistry, PluginRegistryAuditRecord
from zentex.core.execution_spec import ExecutionDomainPlugin
from zentex.core.plugin_base import PluginLifecycleStatus


class ExecutionDomainRegistration(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    spec: ExecutionDomainPlugin
    internal_revision_id: int = Field(ge=1)
    source_kind: Literal["builtin", "user", "test_stub"] = "user"
    description: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @property
    def plugin_id(self) -> str:
        return self.spec.plugin_id


class ExecutionDomainRegistry(AbstractPluginRegistry[ExecutionDomainPlugin]):
    def __init__(self) -> None:
        super().__init__(ExecutionDomainPlugin)
        self._registrations: Dict[str, ExecutionDomainRegistration] = {}
        self._next_internal_revision_id = 1

    def register(
        self,
        plugin: ExecutionDomainPlugin,
        *,
        source_kind: Literal["builtin", "user", "test_stub"] = "user",
        description: Optional[str] = None,
    ) -> Optional[ExecutionDomainRegistration]:
        try:
            normalized = plugin.__class__.model_validate(
                {
                    **plugin.model_dump(),
                    "status": PluginLifecycleStatus.CANDIDATE,
                }
            )
        except ValidationError as exc:
            self._audit_records.append(
                PluginRegistryAuditRecord(
                    plugin_id=getattr(plugin, "plugin_id", "unknown"),
                    action="rejected",
                    audit_reason=str(exc),
                    recorded_at=datetime.now(timezone.utc),
                )
            )
            return None

        runtime_plugin = normalized
        self._plugins[runtime_plugin.plugin_id] = runtime_plugin
        self._audit_records.append(
            PluginRegistryAuditRecord(
                plugin_id=runtime_plugin.plugin_id,
                action="registered",
                audit_reason="registered_as_candidate",
                recorded_at=datetime.now(timezone.utc),
            )
        )
        timestamp = datetime.now(timezone.utc)
        registration = ExecutionDomainRegistration(
            spec=runtime_plugin,
            internal_revision_id=self._next_internal_revision_id,
            source_kind=source_kind,
            description=(description or runtime_plugin.plugin_id),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._next_internal_revision_id += 1
        self._registrations[runtime_plugin.plugin_id] = registration
        return registration

    def list_registrations(self) -> List[ExecutionDomainRegistration]:
        return sorted(self._registrations.values(), key=lambda item: item.plugin_id)
