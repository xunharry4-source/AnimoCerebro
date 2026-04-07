from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.upgrade.plugin.runtime import PluginEvolutionRuntime  # noqa: E402
from zentex.upgrade.management import (  # noqa: E402
    UpgradeLifecycleStatus,
    UpgradeManagementRecord,
    UpgradeManagementStore,
    UpgradeTargetKind,
)


def test_plugin_runtime_copies_candidate_from_source_directory(tmp_path: Path) -> None:
    runtime = PluginEvolutionRuntime()
    source_dir = tmp_path / "source_plugin"
    source_dir.mkdir()
    (source_dir / "plugin.py").write_text("print('source')\n", encoding="utf-8")
    candidate_dir = tmp_path / "source_plugin_candidate_0_5_0_candidate"

    created_path = runtime.copy_plugin_candidate(
        source_plugin_path=str(source_dir),
        candidate_plugin_path=str(candidate_dir),
    )

    assert created_path == str(candidate_dir)
    assert candidate_dir.exists()
    assert (candidate_dir / "plugin.py").read_text(encoding="utf-8") == "print('source')\n"


def test_plugin_runtime_scaffolds_and_cleans_candidate_directory(tmp_path: Path) -> None:
    runtime = PluginEvolutionRuntime()
    candidate_dir = tmp_path / "workspace_anomaly_cluster_candidate"

    created_path = runtime.scaffold_new_plugin_candidate(
        candidate_plugin_path=str(candidate_dir),
    )
    assert created_path == str(candidate_dir)
    assert candidate_dir.exists()

    deleted = runtime.cleanup_candidate_path(candidate_plugin_path=str(candidate_dir))

    assert deleted is True
    assert not candidate_dir.exists()


def test_management_store_requires_real_cancel_handler_for_ongoing_records() -> None:
    store = UpgradeManagementStore(
        records=[
            UpgradeManagementRecord(
                record_id="plugin-upgrade-running-001",
                target_kind=UpgradeTargetKind.PLUGIN,
                action="upgrade",
                target_id="cognitive-tool-router",
                title="Running plugin upgrade",
                reason="Need publication hook updates.",
                trace_id="trace-plugin-upgrade-running-001",
                request_id="request-plugin-upgrade-running-001",
                change_summary="Upgrade in progress.",
                function_summary="Real worker should be cancellable.",
                previous_version="0.4.0",
                current_version="0.4.0",
                candidate_version="0.5.0-candidate",
                current_status=UpgradeLifecycleStatus.RUNNING,
            )
        ]
    )

    called = {"value": False}
    store.register_cancel_handler(
        "plugin-upgrade-running-001",
        lambda: called.__setitem__("value", True),
    )

    record = store.cancel(
        "plugin-upgrade-running-001",
        reason="Operator cancelled the running upgrade.",
    )

    assert called["value"] is True
    assert record.current_status is UpgradeLifecycleStatus.CANCELLED
