from __future__ import annotations

"""Business planner for OpenHands-backed plugin evolution."""

from importlib.util import find_spec
from pathlib import Path

from zentex.upgrade.plugin.models import (
    PluginCreationCandidate,
    PluginCreationExecutionPlan,
    PluginCreationRequest,
    PluginUpgradeCandidate,
    PluginUpgradeExecutionPlan,
    PluginUpgradeRequest,
)
from zentex.upgrade.versioning import UpgradeChangeScope, derive_candidate_version


class OpenHandsRuntimeGuard:
    """Validates the OpenHands SDK dependency."""

    def assert_runtime_ready(self) -> None:
        if find_spec("openhands") is None:
            raise RuntimeError(
                "OpenHands SDK is not installed; configure the plugin upgrade "
                "runtime before running evolution jobs."
            )


class PluginCandidatePathPlanner:
    """Derives isolated candidate paths for plugin evolution."""

    def derive_candidate_plugin_path(
        self,
        source_plugin_path: str,
        candidate_version: str,
    ) -> str:
        source_path = Path(source_plugin_path)
        normalized_version = candidate_version.replace(".", "_").replace("-", "_")
        candidate_name = f"{source_path.name}_candidate_{normalized_version}"
        return str(source_path.with_name(candidate_name))

    def derive_new_plugin_candidate_path(
        self,
        target_root_path: str,
        plugin_id: str,
        candidate_version: str,
    ) -> str:
        root_path = Path(target_root_path)
        plugin_slug = plugin_id.replace(".", "_").replace("-", "_")
        normalized_version = candidate_version.replace(".", "_").replace("-", "_")
        candidate_name = f"{plugin_slug}_candidate_{normalized_version}"
        return str(root_path / candidate_name)


class PluginUpgradePlanner:
    """Builds versioned plugin evolution candidates."""

    def __init__(
        self,
        *,
        runtime_guard: OpenHandsRuntimeGuard | None = None,
        path_planner: PluginCandidatePathPlanner | None = None,
    ) -> None:
        self._runtime_guard = runtime_guard or OpenHandsRuntimeGuard()
        self._path_planner = path_planner or PluginCandidatePathPlanner()

    def plan_candidate(self, request: PluginUpgradeRequest) -> PluginUpgradeCandidate:
        self._runtime_guard.assert_runtime_ready()

        candidate_version = derive_candidate_version(
            request.baseline_version,
            request.change_scope,
        )
        candidate_plugin_path = self._path_planner.derive_candidate_plugin_path(
            request.plugin_path,
            candidate_version,
        )
        execution_plan = PluginUpgradeExecutionPlan(
            source_plugin_path=request.plugin_path,
            candidate_plugin_path=candidate_plugin_path,
            allowed_write_paths=[candidate_plugin_path],
            startup_commands=request.startup_commands,
            validation_commands=request.validation_commands,
            requested_capabilities=request.requested_capabilities,
        )
        return PluginUpgradeCandidate(
            plugin_id=request.plugin_id,
            source_plugin_path=request.plugin_path,
            candidate_plugin_path=candidate_plugin_path,
            baseline_version=request.baseline_version,
            candidate_version=candidate_version,
            goal=request.goal,
            execution_plan=execution_plan,
            release_gate=[
                "The source plugin must be copied before any automated change starts.",
                "Only the candidate plugin copy may receive automated writes.",
                "The copied candidate must bump its version metadata before mutation.",
                "Startup and validation commands must pass before promotion.",
                "The evolved candidate must register as a non-active version first.",
            ],
        )

    def plan_new_candidate(
        self,
        request: PluginCreationRequest,
    ) -> PluginCreationCandidate:
        self._runtime_guard.assert_runtime_ready()

        candidate_version = derive_candidate_version(
            request.initial_version,
            UpgradeChangeScope.PATCH,
        )
        candidate_plugin_path = self._path_planner.derive_new_plugin_candidate_path(
            request.target_root_path,
            request.plugin_id,
            candidate_version,
        )
        execution_plan = PluginCreationExecutionPlan(
            candidate_plugin_path=candidate_plugin_path,
            allowed_write_paths=[candidate_plugin_path],
            startup_commands=request.startup_commands,
            validation_commands=request.validation_commands,
            requested_capabilities=request.requested_capabilities,
        )
        return PluginCreationCandidate(
            plugin_id=request.plugin_id,
            candidate_plugin_path=candidate_plugin_path,
            initial_version=request.initial_version,
            candidate_version=candidate_version,
            goal=request.goal,
            execution_plan=execution_plan,
            release_gate=[
                "The new plugin must be created as a candidate scaffold, not as an active plugin.",
                "Only the candidate plugin directory may receive automated writes.",
                "Startup and validation commands must pass before registration.",
                "The created candidate must register as a non-active version first.",
            ],
        )

    def assert_runtime_ready(self) -> None:
        self._runtime_guard.assert_runtime_ready()
