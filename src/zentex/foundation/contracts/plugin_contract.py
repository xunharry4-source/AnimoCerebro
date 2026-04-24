"""Plugin lifecycle contracts and health reporting models."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import Field

from zentex.foundation.contracts.base_models import ZentexBaseModel
from zentex.foundation.meta.feature_family import FeatureFamily

UTC = timezone.utc


class PluginStatus(str, Enum):
    unregistered = "unregistered"
    registered = "registered"
    active = "active"
    degraded = "degraded"
    disabled = "disabled"


class PluginContract(ZentexBaseModel):
    """Immutable descriptor for a registered plugin."""

    plugin_id: str
    name: str
    version: str
    family: FeatureFamily
    status: PluginStatus = PluginStatus.unregistered
    description: str = ""


class PluginHealthReport(ZentexBaseModel):
    """Point-in-time health snapshot for a plugin."""

    plugin_id: str
    status: PluginStatus
    latency_ms: float = 0.0
    error_rate: float = 0.0
    last_checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: str = ""
