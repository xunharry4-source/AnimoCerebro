"""StartupSnapshotBuilder — assembles the startup context snapshot."""

from datetime import datetime, timezone
from typing import Any

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

        Args:
            session_id: The active session identifier (forwarded to bridge).

        Returns:
            A dict with keys: session_id, environment, plugins, identity,
            capabilities, built_at.
        """
        environment: dict = {}
        try:
            environment = self._bridge.get_environment_state(session_id) or {}
        except Exception:  # noqa: BLE001
            pass

        plugins: list[dict] = []
        try:
            plugins = self._bridge.get_registered_plugins() or []
        except Exception:  # noqa: BLE001
            pass

        identity: dict = {}
        try:
            identity = self._bridge.get_system_identity() or {}
        except Exception:  # noqa: BLE001
            pass

        capabilities: list[dict] = []
        try:
            capabilities = self._bridge.get_capability_directory() or []
        except Exception:  # noqa: BLE001
            pass

        return {
            "session_id": session_id,
            "environment": environment,
            "plugins": plugins,
            "identity": identity,
            "capabilities": capabilities,
            "built_at": datetime.now(UTC).isoformat(),
        }
