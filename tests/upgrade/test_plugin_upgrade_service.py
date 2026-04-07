from __future__ import annotations

from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.upgrade.plugin.models import PluginUpgradeRequest  # noqa: E402
from zentex.upgrade.plugin.service import OpenHandsPluginUpgradeService  # noqa: E402


def test_plugin_upgrade_request_requires_explicit_write_scope() -> None:
    with pytest.raises(ValueError, match="allowed_write_paths must not be empty"):
        PluginUpgradeRequest(
            plugin_id="cognitive-tool-router",
            plugin_path="src/zentex/runtime/cognitive_tools",
            baseline_version="0.4.0",
            goal="Add structured upgrade publication hooks.",
        )


def test_plugin_upgrade_service_fails_closed_when_openhands_is_missing() -> None:
    service = OpenHandsPluginUpgradeService()
    request = PluginUpgradeRequest(
        plugin_id="cognitive-tool-router",
        plugin_path="src/zentex/runtime/cognitive_tools",
        baseline_version="0.4.0",
        goal="Add structured upgrade publication hooks.",
        allowed_write_paths=[
            "src/zentex/runtime/cognitive_tools",
            "tests/runtime",
        ],
        validation_commands=["pytest tests/runtime/test_cognitive_tool_registry.py -q"],
        startup_commands=["uvicorn zentex.web_console.app:app --reload"],
    )

    with pytest.raises(RuntimeError, match="OpenHands SDK is not installed"):
        service.plan_candidate(request)


def test_plugin_upgrade_service_plans_copy_then_bump_version_strategy() -> None:
    service = OpenHandsPluginUpgradeService()
    service.assert_runtime_ready = lambda: None  # type: ignore[method-assign]
    request = PluginUpgradeRequest(
        plugin_id="cognitive-tool-router",
        plugin_path="src/zentex/runtime/cognitive_tools",
        baseline_version="0.4.0",
        goal="Add structured upgrade publication hooks.",
        allowed_write_paths=[
            "src/zentex/runtime/cognitive_tools",
            "tests/runtime",
        ],
        validation_commands=["pytest tests/runtime/test_cognitive_tool_registry.py -q"],
        startup_commands=["uvicorn zentex.web_console.app:app --reload"],
    )

    candidate = service.plan_candidate(request)

    assert candidate.source_plugin_path == "src/zentex/runtime/cognitive_tools"
    assert candidate.candidate_plugin_path != candidate.source_plugin_path
    assert candidate.candidate_version == "0.5.0-candidate"
    assert candidate.execution_plan.version_update_strategy == "copy_then_bump_version"
    assert candidate.execution_plan.allowed_write_paths == [candidate.candidate_plugin_path]
    assert "copied before any automated change starts" in candidate.release_gate[0]
