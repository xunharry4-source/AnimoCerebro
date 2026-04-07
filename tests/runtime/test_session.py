from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.runtime.session import BrainSession, BrainSessionSnapshot  # noqa: E402
from zentex.runtime.transcript import (  # noqa: E402
    BrainTranscriptEntryType,
    BrainTranscriptStore,
)


def test_session_initialization_and_snapshot(tmp_path: Path) -> None:
    store = BrainTranscriptStore(tmp_path / "brain_transcript.jsonl")
    session = BrainSession(session_id="session-init", store=store)

    assert session.turn_counter == 0
    assert session.created_at is None
    assert session.current_workspace is None
    assert session.active_goal_frame is None
    assert session.last_working_memory is None
    assert session.last_temporal_agenda is None
    assert session.last_living_self_model is None
    assert session.last_metacognition is None
    assert session.last_conflict_snapshot is None
    assert session.last_counterfactual_simulation is None
    assert session.last_interaction_mind is None
    assert session.last_consolidation is None
    assert session.last_reflection is None
    assert session.last_turn_at is None

    snapshot = session.get_snapshot()

    assert isinstance(snapshot, BrainSessionSnapshot)
    assert snapshot.session_id == "session-init"
    assert snapshot.turn_count == 0
    assert snapshot.active_goal_titles == []
    assert snapshot.current_focus_summary is None
    assert snapshot.overdue_items == []
    assert snapshot.current_reasoning_mode is None
    assert snapshot.degraded_flags == []
    assert snapshot.last_turn_at is None


def test_session_advance_turn(tmp_path: Path) -> None:
    transcript_path = tmp_path / "brain_transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    session = BrainSession(session_id="session-advance", store=store)
    turn_timestamp = datetime(2026, 4, 3, 14, 0, tzinfo=timezone.utc)
    turn_result = {
        "turn_id": "turn-001",
        "trace_id": "trace-001",
        "timestamp": turn_timestamp,
        "current_workspace": {"cwd": "/workspace/demo"},
        "active_goal_frame": {
            "goals": [{"title": "Stabilize transcript replay"}],
        },
        "context_snapshot": {
            "workspace": {"cwd": "/workspace/demo"},
            "active_goal_frame": {
                "goals": [{"title": "Stabilize transcript replay"}],
            },
        },
        "working_memory": {
            "current_focus_summary": "Validate transcript durability",
            "evidence": ["evt-1"],
        },
        "temporal_agenda": {
            "overdue_items": ["replay regression check"],
        },
        "metacognition": {
            "current_reasoning_mode": "deliberate",
            "degraded_flags": ["cache_cold"],
        },
        "status": "completed",
    }

    returned_turn_id = session.advance_turn(turn_result)

    assert returned_turn_id == "turn-001"
    assert session.turn_counter == 1
    assert session.created_at == turn_timestamp
    assert session.last_turn_at == turn_timestamp
    assert session.current_workspace == {"cwd": "/workspace/demo"}
    assert session.active_goal_frame == {
        "goals": [{"title": "Stabilize transcript replay"}],
    }
    assert session.last_working_memory == {
        "current_focus_summary": "Validate transcript durability",
        "evidence": ["evt-1"],
    }
    assert session.last_temporal_agenda == {
        "overdue_items": ["replay regression check"],
    }
    assert session.last_metacognition == {
        "current_reasoning_mode": "deliberate",
        "degraded_flags": ["cache_cold"],
    }

    persisted_entries = store.read_by_session_id("session-advance")
    assert [entry.entry_type for entry in persisted_entries] == [
        BrainTranscriptEntryType.SESSION_STARTED,
        BrainTranscriptEntryType.TURN_STARTED,
        BrainTranscriptEntryType.CONTEXT_SNAPSHOT_WRITTEN,
        BrainTranscriptEntryType.WORKING_MEMORY_UPDATED,
        BrainTranscriptEntryType.TEMPORAL_AGENDA_UPDATED,
        BrainTranscriptEntryType.METACOGNITION_DECIDED,
        BrainTranscriptEntryType.TURN_FINISHED,
    ]
    assert all(entry.session_id == "session-advance" for entry in persisted_entries)
    assert all(entry.turn_id == "turn-001" for entry in persisted_entries)
    assert persisted_entries[3].payload == {
        "current_focus_summary": "Validate transcript durability",
        "evidence": ["evt-1"],
    }
    assert persisted_entries[5].payload == {
        "current_reasoning_mode": "deliberate",
        "degraded_flags": ["cache_cold"],
    }

    file_lines = transcript_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(file_lines) == len(persisted_entries)


def test_session_restore_from_transcript(tmp_path: Path) -> None:
    store = BrainTranscriptStore(tmp_path / "brain_transcript.jsonl")
    session_id = "session-restore"

    first_turn_at = datetime(2026, 4, 3, 15, 0, tzinfo=timezone.utc)
    second_turn_at = datetime(2026, 4, 3, 15, 5, tzinfo=timezone.utc)

    store.write_entry(
        session_id=session_id,
        turn_id="turn-1",
        entry_type=BrainTranscriptEntryType.SESSION_STARTED,
        timestamp=first_turn_at,
        payload={
            "workspace": {"cwd": "/workspace/restore"},
            "active_goal_frame": {
                "goals": [{"title": "Recover session state"}],
            },
        },
        source="brain_session",
        trace_id="trace-restore",
    )
    store.write_entry(
        session_id=session_id,
        turn_id="turn-1",
        entry_type=BrainTranscriptEntryType.TURN_STARTED,
        timestamp=first_turn_at,
        payload={"turn_index": 1, "workspace": {"cwd": "/workspace/restore"}},
        source="brain_session",
        trace_id="trace-restore",
    )
    store.write_entry(
        session_id=session_id,
        turn_id="turn-1",
        entry_type=BrainTranscriptEntryType.WORKING_MEMORY_UPDATED,
        timestamp=first_turn_at,
        payload={"current_focus_summary": "first focus"},
        source="think_loop",
        trace_id="trace-restore",
    )
    store.write_entry(
        session_id="session-noise",
        turn_id="turn-noise",
        entry_type=BrainTranscriptEntryType.TURN_STARTED,
        timestamp=first_turn_at,
        payload={"turn_index": 99},
        source="brain_session",
        trace_id="trace-noise",
    )
    store.write_entry(
        session_id=session_id,
        turn_id="turn-2",
        entry_type=BrainTranscriptEntryType.TURN_STARTED,
        timestamp=second_turn_at,
        payload={"turn_index": 2, "workspace": {"cwd": "/workspace/restore"}},
        source="brain_session",
        trace_id="trace-restore",
    )
    store.write_entry(
        session_id=session_id,
        turn_id="turn-2",
        entry_type=BrainTranscriptEntryType.WORKING_MEMORY_UPDATED,
        timestamp=second_turn_at,
        payload={
            "current_focus_summary": "latest focus",
            "evidence": ["evt-latest"],
        },
        source="think_loop",
        trace_id="trace-restore",
    )
    store.write_entry(
        session_id=session_id,
        turn_id="turn-2",
        entry_type=BrainTranscriptEntryType.METACOGNITION_DECIDED,
        timestamp=second_turn_at,
        payload={
            "current_reasoning_mode": "reflective",
            "degraded_flags": ["memory_pressure"],
        },
        source="think_loop",
        trace_id="trace-restore",
    )

    restored_session = BrainSession(session_id=session_id, store=store)
    restored_session.restore_from_transcript()

    assert restored_session.created_at == first_turn_at
    assert restored_session.turn_counter == 2
    assert restored_session.current_workspace == {"cwd": "/workspace/restore"}
    assert restored_session.active_goal_frame == {
        "goals": [{"title": "Recover session state"}],
    }
    assert restored_session.last_working_memory == {
        "current_focus_summary": "latest focus",
        "evidence": ["evt-latest"],
    }
    assert restored_session.last_metacognition == {
        "current_reasoning_mode": "reflective",
        "degraded_flags": ["memory_pressure"],
    }
    assert restored_session.last_turn_at == second_turn_at

    snapshot = restored_session.get_snapshot()
    assert snapshot.turn_count == 2
    assert snapshot.active_goal_titles == ["Recover session state"]
    assert snapshot.current_focus_summary == "latest focus"
    assert snapshot.current_reasoning_mode == "reflective"
    assert snapshot.degraded_flags == ["memory_pressure"]
    assert snapshot.last_turn_at == second_turn_at
