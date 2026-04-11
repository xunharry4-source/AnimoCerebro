from __future__ import annotations

from zentex.core.plugin_base import PluginHealthStatus, PluginLifecycleStatus
from zentex.core.sensory_spec import SignalIngestPlugin


class BasicWebhookIngestPlugin(SignalIngestPlugin):
    source_kind: str = "webhook"
    _payload: str

    def __init__(self, payload: str, **data: object) -> None:
        super().__init__(**data)
        object.__setattr__(self, "_payload", payload)

    def ingest_signal(self) -> str:
        return self._payload


def build_default_webhook_ingest_plugin(
    *,
    payload: str = "web console seeded sensory payload",
    plugin_id: str = "sensory-ingest-webhook",
    version: str = "1.0.0",
    status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> BasicWebhookIngestPlugin:
    return BasicWebhookIngestPlugin(
        payload=payload,
        plugin_id=plugin_id,
        version=version,
        feature_code="sensory.ingest",
        is_concurrency_safe=True,
        status=status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["webhook_parse_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )