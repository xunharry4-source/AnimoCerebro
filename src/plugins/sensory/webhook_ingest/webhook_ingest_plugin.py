from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from zentex.plugins.models import PluginLifecycleStatus


class BasicWebhookIngestPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = "sensory_webhook"
    version: str = "1.0.0"
    feature_code: str = "sensory.ingest"
    display_name: str = "Webhook Ingest"
    description: str = "Produce a seeded sensory payload for Q1 ingestion."
    behavior_key: str = "sensory_webhook"
    lifecycle_status: str = PluginLifecycleStatus.CANDIDATE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    payload: str = "web console seeded sensory payload"

    def ingest_signal(self) -> str:
        return self.payload


def build_default_webhook_ingest_plugin() -> BasicWebhookIngestPlugin:
    return BasicWebhookIngestPlugin()
