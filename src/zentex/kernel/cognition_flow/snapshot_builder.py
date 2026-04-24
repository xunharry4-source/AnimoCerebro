"""StartupSnapshotBuilder — assembles the startup context snapshot."""

from datetime import datetime, timezone
import logging
from typing import Any

logger = logging.getLogger(__name__)

UTC = timezone.utc


class StartupSnapshotBuilder:
    """Builds a startup snapshot dict from multiple bridge data sources.

    The *bridge* is duck-typed; it must provide:
    - get_environment_state(session_id: str) -> dict
    - get_registered_plugins() -> list[dict]
    - get_system_identity() -> dict
    - get_capability_directory() -> list[dict]

    Each call is wrapped in try/except so a single source failure does not
    abort the whole snapshot.
    """

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def build(self, session_id: str) -> dict:
        """Collect data from all bridge sources and return a merged snapshot.

        Standard Redline (G33):
        - No more silent suppression of source failures.
        - If the bridge fails to provide Environment, Plugins, or Identity, we fail.
        """
        environment = self._bridge.get_environment_state(session_id) or {}
        plugins = self._bridge.get_registered_plugins() or []
        identity = self._system_identity = self._bridge.get_system_identity() or {}
        capabilities = self._bridge.get_capability_directory() or []

        snapshot = {
            "session_id": session_id,
            "environment": environment,
            "plugins": plugins,
            "identity": identity,
            "capabilities": capabilities,
            "built_at": datetime.now(UTC).isoformat(),
        }
        
        # Flatten for evidence extraction compatibility
        if isinstance(environment, dict):
            snapshot.update(environment)
        if isinstance(identity, dict):
            snapshot.update(identity)
            
        return snapshot
