from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zentex.runtime.transcript import (  # noqa: E402
    BrainTranscriptEntry,
    BrainTranscriptEntryType,
    BrainTranscriptStore,
)


def _read_jsonl_lines(file_path: Path) -> list[dict[str, object]]:
    with file_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_append_and_read_single_entry(tmp_path: Path) -> None:
    transcript_path = tmp_path / "brain_transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    timestamp = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
    entry = BrainTranscriptEntry(
        entry_id="entry-1",
        session_id="session-alpha",
        turn_id="turn-1",
        entry_type=BrainTranscriptEntryType.SESSION_STARTED,
        timestamp=timestamp,
        payload={"scope": "alpha", "status": "booted"},
        source="runtime",
        trace_id="trace-1",
    )

    store.append_entry(entry)

    loaded_entries = store.read_by_session_id("session-alpha")
    assert len(loaded_entries) == 1

    loaded_entry = loaded_entries[0]
    assert loaded_entry == entry
    assert loaded_entry.entry_type is BrainTranscriptEntryType.SESSION_STARTED
    assert isinstance(loaded_entry.timestamp, datetime)
    assert loaded_entry.timestamp == timestamp

    jsonl_records = _read_jsonl_lines(transcript_path)
    assert len(jsonl_records) == 1
    assert jsonl_records[0]["entry_type"] == "session_started"
    assert jsonl_records[0]["timestamp"] == timestamp.isoformat()


def test_retrieve_by_session_id(tmp_path: Path) -> None:
    transcript_path = tmp_path / "brain_transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    session_id = "session-restore"
    base_timestamp = datetime(2026, 4, 3, 12, 30, tzinfo=timezone.utc)

    store.write_entry(
        entry_id="entry-1",
        session_id=session_id,
        turn_id="turn-a",
        entry_type=BrainTranscriptEntryType.SESSION_STARTED,
        timestamp=base_timestamp,
        payload={"stage": "session_started"},
        source="runtime",
        trace_id="trace-restore",
    )
    store.write_entry(
        entry_id="entry-2",
        session_id="session-noise",
        turn_id="turn-noise",
        entry_type=BrainTranscriptEntryType.SESSION_STARTED,
        timestamp=base_timestamp.replace(minute=31),
        payload={"stage": "noise"},
        source="runtime",
        trace_id="trace-noise",
    )
    store.write_entry(
        entry_id="entry-3",
        session_id=session_id,
        turn_id="turn-a",
        entry_type=BrainTranscriptEntryType.TURN_STARTED,
        timestamp=base_timestamp.replace(minute=32),
        payload={"stage": "turn_started"},
        source="runtime",
        trace_id="trace-restore",
    )
    store.write_entry(
        entry_id="entry-4",
        session_id=session_id,
        turn_id="turn-a",
        entry_type=BrainTranscriptEntryType.TURN_FINISHED,
        timestamp=base_timestamp.replace(minute=33),
        payload={"stage": "turn_finished"},
        source="runtime",
        trace_id="trace-restore",
    )

    loaded_entries = store.read_by_session_id(session_id)

    assert len(loaded_entries) == 3
    assert [entry.entry_id for entry in loaded_entries] == ["entry-1", "entry-3", "entry-4"]
    assert [entry.entry_type for entry in loaded_entries] == [
        BrainTranscriptEntryType.SESSION_STARTED,
        BrainTranscriptEntryType.TURN_STARTED,
        BrainTranscriptEntryType.TURN_FINISHED,
    ]
    assert [entry.timestamp for entry in loaded_entries] == [
        base_timestamp,
        base_timestamp.replace(minute=32),
        base_timestamp.replace(minute=33),
    ]

    jsonl_records = _read_jsonl_lines(transcript_path)
    assert len(jsonl_records) == 4
    assert [record["entry_id"] for record in jsonl_records] == [
        "entry-1",
        "entry-2",
        "entry-3",
        "entry-4",
    ]


def test_retrieve_by_turn_id(tmp_path: Path) -> None:
    transcript_path = tmp_path / "brain_transcript.jsonl"
    store = BrainTranscriptStore(transcript_path)
    turn_id = "turn-replay"
    timestamp = datetime(2026, 4, 3, 13, 0, tzinfo=timezone.utc)

    store.write_entry(
        entry_id="entry-1",
        session_id="session-replay",
        turn_id=turn_id,
        entry_type=BrainTranscriptEntryType.CONTEXT_SNAPSHOT_WRITTEN,
        timestamp=timestamp,
        payload={"context": {"goal": "triage"}},
        source="think-loop",
        trace_id="trace-replay",
    )
    store.write_entry(
        entry_id="entry-2",
        session_id="session-replay",
        turn_id=turn_id,
        entry_type=BrainTranscriptEntryType.METACOGNITION_DECIDED,
        timestamp=timestamp.replace(minute=1),
        payload={"decision": "invoke_tool"},
        source="metacognition",
        trace_id="trace-replay",
    )
    store.write_entry(
        entry_id="entry-3",
        session_id="session-other",
        turn_id="turn-other",
        entry_type=BrainTranscriptEntryType.COGNITIVE_TOOL_COMPLETED,
        timestamp=timestamp.replace(minute=2),
        payload={"tool": "search"},
        source="tool-runner",
        trace_id="trace-other",
    )

    loaded_entries = store.read_by_turn_id(turn_id)

    assert len(loaded_entries) == 2
    assert [entry.entry_id for entry in loaded_entries] == ["entry-1", "entry-2"]
    assert [entry.entry_type for entry in loaded_entries] == [
        BrainTranscriptEntryType.CONTEXT_SNAPSHOT_WRITTEN,
        BrainTranscriptEntryType.METACOGNITION_DECIDED,
    ]
    assert all(isinstance(entry.timestamp, datetime) for entry in loaded_entries)
    assert all(entry.turn_id == turn_id for entry in loaded_entries)

    jsonl_records = _read_jsonl_lines(transcript_path)
    assert len(jsonl_records) == 3
    assert jsonl_records[0]["entry_type"] == "context_snapshot_written"
    assert jsonl_records[1]["entry_type"] == "metacognition_decided"
