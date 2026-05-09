from __future__ import annotations

"""
OpenHands-backed plugin upgrade planner.

This service is the core entrypoint for plugin evolution. It validates the
write scope, checks that the OpenHands runtime is available, and emits a
candidate plan for isolated code evolution and post-change verification. The
source plugin stays untouched; the evolution workflow must first clone the
plugin into a versioned candidate directory and only mutate that copy.
"""

from typing import Any, Union

from zentex.upgrade.plugin.models import (
    PluginCreationCandidate,
    PluginCreationRequest,
    PluginUpgradeCandidate,
    PluginUpgradeRequest,
)
from zentex.upgrade.plugin.planner import PluginCandidatePathPlanner, PluginUpgradePlanner


class OpenHandsPluginUpgradeService:
    """Fail-closed planner for OpenHands-driven plugin evolution candidates."""

    def __init__(self, *, planner: PluginUpgradePlanner | None = None) -> None:
        self._planner = planner or PluginUpgradePlanner()
        self._path_planner = PluginCandidatePathPlanner()

    def assert_runtime_ready(self) -> None:
        self._planner.assert_runtime_ready()

    def derive_candidate_plugin_path(
        self,
        source_plugin_path: str,
        candidate_version: str,
    ) -> str:
        """
        Build a versioned plugin copy path for the candidate upgrade.

        The candidate directory sits next to the source plugin so the evolution
        worker can copy the original payload, bump version metadata, and keep
        all subsequent writes away from the active source directory.
        """

        return self._path_planner.derive_candidate_plugin_path(
            source_plugin_path,
            candidate_version,
        )

    def derive_new_plugin_candidate_path(
        self,
        target_root_path: str,
        plugin_id: str,
        candidate_version: str,
    ) -> str:
        """
        Build the versioned directory path for a new plugin candidate scaffold.

        New plugins are created as candidate directories under the target root
        so they can be validated and audited before registration.
        """

        return self._path_planner.derive_new_plugin_candidate_path(
            target_root_path,
            plugin_id,
            candidate_version,
        )

    def plan_candidate(self, request: PluginUpgradeRequest) -> PluginUpgradeCandidate:
        return self._planner.plan_candidate(request)

    def plan_new_candidate(
        self,
        request: PluginCreationRequest,
    ) -> PluginCreationCandidate:
        return self._planner.plan_new_candidate(request)

    def update_plugin_metadata(self, candidate_path: str, new_version: str) -> bool:
        from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime

        return PluginEvolutionRuntime().update_plugin_metadata(candidate_path, new_version)

    def execute_openhands_evolution(self, candidate: Union[PluginUpgradeCandidate, PluginCreationCandidate]) -> dict[str, Any]:
        """Autonomous code generation and evolution logic (Function 60 gap)."""
        self.assert_runtime_ready()
        raise RuntimeError(
            "OpenHands plugin evolution requires a real SDK worker result with diff, validation, "
            "permission scan, and health probe evidence; heuristic scaffold generation is forbidden."
        )
