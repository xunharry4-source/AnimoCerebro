from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.memory.enhanced import (  # noqa: E402
    EnhancedMemoryRecord,
    EnhancedMemoryService,
)
from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.transcript import (  # noqa: E402
    BrainTranscriptEntryType,
    BrainTranscriptStore,
)


class FakeSemanticSink:
    """Test double that records semantic/procedural memory writes."""

    def __init__(self) -> None:
        self.semantic_records: list[EnhancedMemoryRecord] = []
        self.procedural_records: list[EnhancedMemoryRecord] = []

    def store_semantic_memory(self, record: EnhancedMemoryRecord) -> None:
        self.semantic_records.append(record)

    def store_procedural_memory(self, record: EnhancedMemoryRecord) -> None:
        self.procedural_records.append(record)


class FakeEpisodeSink:
    """Test double that records episodic graph writes."""

    def __init__(self) -> None:
        self.episodes: list[EnhancedMemoryRecord] = []

    def add_episode(self, record: EnhancedMemoryRecord) -> None:
        self.episodes.append(record)


def test_transcript_listener_projects_entries_into_enhanced_memory(
    tmp_path: Path,
) -> None:
    semantic_sink = FakeSemanticSink()
    episode_sink = FakeEpisodeSink()
    memory_service = EnhancedMemoryService(
        semantic_store_path=tmp_path / "semantic.jsonl",
        procedural_store_path=tmp_path / "procedural.jsonl",
        episodic_store_path=tmp_path / "episodic.jsonl",
        semantic_sink=semantic_sink,
        procedural_sink=semantic_sink,
        episodic_sink=episode_sink,
    )
    transcript_store = BrainTranscriptStore(
        tmp_path / "brain_transcript.jsonl",
        entry_listeners=[memory_service.ingest_transcript_entry],
    )

    transcript_store.write_entry(
        session_id="session-1",
        turn_id="turn-1",
        entry_type=BrainTranscriptEntryType.CONSOLIDATION_COMPLETED,
        payload={
            "summary": "Timeout recovery pattern promoted into durable memory.",
            "status": "completed",
        },
        source="memory.consolidation",
        trace_id="trace-memory-001",
    )

    semantic_records = memory_service.list_semantic_records()
    procedural_records = memory_service.list_procedural_records()
    episodic_records = memory_service.list_episodic_records()
    assert len(semantic_records) == 1
    assert len(procedural_records) == 1
    assert len(episodic_records) == 1
    assert semantic_records[0].trace_id == "trace-memory-001"
    assert procedural_records[0].summary == "Timeout recovery pattern promoted into durable memory."
    assert episodic_records[0].tags[-1] == "episode"
    assert len(semantic_sink.semantic_records) == 1
    assert len(semantic_sink.procedural_records) == 1
    assert len(episode_sink.episodes) == 1
    hits = memory_service.recall(query="timeout recovery", trace_id="trace-memory-001")
    assert hits
    assert hits[0].trace_id == "trace-memory-001"


def test_runtime_auto_attaches_memory_projection_listener(tmp_path: Path) -> None:
    memory_service = EnhancedMemoryService(
        semantic_store_path=tmp_path / "runtime_semantic.jsonl",
        procedural_store_path=tmp_path / "runtime_procedural.jsonl",
        episodic_store_path=tmp_path / "runtime_episodic.jsonl",
    )
    transcript_store = BrainTranscriptStore(tmp_path / "runtime_transcript.jsonl")
    runtime = BrainRuntime(
        transcript_store=transcript_store,
        runtime_memory_store=memory_service,
    )

    runtime.transcript_store.write_entry(
        session_id="session-2",
        turn_id="turn-2",
        entry_type=BrainTranscriptEntryType.DECISION_SYNTHESIZED,
        payload={"summary": "Selected the safer remediation branch."},
        source="runtime.think_loop",
        trace_id="trace-runtime-attach-001",
    )

    semantic_records = memory_service.list_semantic_records()
    procedural_records = memory_service.list_procedural_records()
    assert len(semantic_records) == 1
    assert len(procedural_records) == 1
    assert runtime.transcript_store.list_listener_failures() == []


def test_memory_records_can_be_governed_with_audit_and_filtered_recall(tmp_path: Path) -> None:
    memory_service = EnhancedMemoryService(
        semantic_store_path=tmp_path / "managed_semantic.jsonl",
        procedural_store_path=tmp_path / "managed_procedural.jsonl",
        episodic_store_path=tmp_path / "managed_episodic.jsonl",
        management_store_path=tmp_path / "managed_state.json",
        audit_store_path=tmp_path / "managed_audit.jsonl",
    )
    transcript_store = BrainTranscriptStore(
        tmp_path / "managed_transcript.jsonl",
        entry_listeners=[memory_service.ingest_transcript_entry],
    )

    transcript_store.write_entry(
        session_id="session-managed",
        turn_id="turn-managed",
        entry_type=BrainTranscriptEntryType.DECISION_SYNTHESIZED,
        payload={"summary": "Promote the rollback-safe branch."},
        source="runtime.think_loop",
        trace_id="trace-managed-001",
    )
    managed = memory_service.list_managed_records(limit=10)
    assert managed
    managed_record = managed[0]
    assert managed_record.status == "active"

    updated = memory_service.update_management_state(
        managed_record.memory_id,
        trust_level="suspect",
        management_note="Needs human review before reuse.",
        correction_note="Observed conflicting branch evidence in later runs.",
        operator="tester",
        reason="Flagged after trace review.",
    )
    assert updated.trust_level == "suspect"
    assert updated.management_note == "Needs human review before reuse."
    assert updated.correction_note == "Observed conflicting branch evidence in later runs."

    audit = memory_service.list_audit_events(memory_id=managed_record.memory_id, limit=10)
    assert any(event.action == "trust_changed:suspect" for event in audit)
    filtered = memory_service.list_managed_records(trust_level="suspect", limit=10)
    assert any(item.memory_id == managed_record.memory_id for item in filtered)

    archived = memory_service.update_management_state(
        managed_record.memory_id,
        status="archived",
        visibility="hidden",
        operator="tester",
        reason="No longer reusable.",
    )
    assert archived.status == "archived"
    assert archived.visibility == "hidden"
    for item in memory_service.list_managed_records(limit=10):
        memory_service.update_management_state(
            item.memory_id,
            status="archived",
            visibility="hidden",
            operator="tester",
            reason="Archive full trace before recall.",
        )
    assert memory_service.recall(query="rollback-safe", limit=10) == []
