from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.memory.enhanced import EnhancedMemoryService  # noqa: E402
from zentex.upgrade.evidence import UpgradeEvidenceService  # noqa: E402
from zentex.upgrade.ledger import UpgradeAuditStore, UpgradeMemoryStore  # noqa: E402
from zentex.upgrade.management import (  # noqa: E402
    UpgradeLifecycleStatus,
    UpgradeManagementRecord,
    UpgradeTargetKind,
)


def test_upgrade_evidence_projects_records_into_enhanced_memory(
    tmp_path: Path,
) -> None:
    enhanced_memory = EnhancedMemoryService(
        semantic_store_path=tmp_path / "semantic.jsonl",
        procedural_store_path=tmp_path / "procedural.jsonl",
        episodic_store_path=tmp_path / "episodic.jsonl",
    )
    evidence_service = UpgradeEvidenceService(
        audit_store=UpgradeAuditStore(tmp_path / "audit.jsonl"),
        memory_store=UpgradeMemoryStore(tmp_path / "memory.jsonl"),
        enhanced_memory_service=enhanced_memory,
    )
    record = UpgradeManagementRecord(
        record_id="record-upgrade-001",
        target_kind=UpgradeTargetKind.PLUGIN,
        action="upgrade",
        target_id="plugins.router",
        title="Plugin upgrade for router",
        reason="Need stronger upgrade routing and evidence projection.",
        trace_id="trace-upgrade-memory-001",
        request_id="request-upgrade-memory-001",
        source_event_id="signal-upgrade-001",
        change_summary="Upgrade completed with the real worker path.",
        function_summary="Promote candidate plugin after validation.",
        previous_version="1.2.0",
        current_version="1.2.0",
        candidate_version="1.2.1-candidate",
        current_status=UpgradeLifecycleStatus.COMPLETED,
        current_progress=100,
        success_stage="plugin_upgrade",
        success_summary="plugin_upgrade completed successfully.",
        reusable_insight="Copying source to candidate first avoided mutating the active plugin.",
        successful_command="pytest tests/runtime/test_cognitive_tool_registry.py -q",
        success_artifact_refs=["plugins/router_candidate"],
        promotion_hint="Reuse the candidate-copy path for future plugin upgrades.",
        success_tags=["plugin", "upgrade", "plugin_upgrade", "success"],
        evidence_refs=["audits/plugin_upgrade.json"],
    )

    evidence_service.record_event(
        record,
        event_type="plugin_upgrade_completed",
        summary="Plugin upgrade finished and wrote durable evidence.",
    )

    semantic_records = enhanced_memory.list_semantic_records()
    procedural_records = enhanced_memory.list_procedural_records()
    episodic_records = enhanced_memory.list_episodic_records()
    assert len(semantic_records) == 1
    assert len(procedural_records) == 1
    assert len(episodic_records) == 1
    assert semantic_records[0].target_id == "plugins.router"
    assert procedural_records[0].version_id == "1.2.1-candidate"
    assert "provenance" in episodic_records[0].tags
    recall_hits = enhanced_memory.recall(
        query="mutating the active plugin",
        trace_id="trace-upgrade-memory-001",
        target_id="plugins.router",
    )
    assert recall_hits
