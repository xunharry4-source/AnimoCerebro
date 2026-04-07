from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest


fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from zentex.runtime.transcript import BrainTranscriptEntryType  # noqa: E402
from zentex.web_console import dev_server  # noqa: E402


def _fresh_client() -> TestClient:
    module = importlib.reload(dev_server)
    return TestClient(module.app)


def test_events_stream_idle_disconnect_is_handled_cleanly() -> None:
    client = _fresh_client()
    runtime = client.app.state.runtime
    existing_entries = list(runtime.transcript_store.iter_entries())
    assert existing_entries
    last_entry_id = existing_entries[-1].entry_id

    with client.websocket_connect(f"/api/web/events/stream?last_entry_id={last_entry_id}") as websocket:
        websocket.close()


def test_events_stream_without_cursor_is_delta_only() -> None:
    client = _fresh_client()
    runtime = client.app.state.runtime

    with client.websocket_connect("/api/web/events/stream") as websocket:
        runtime.transcript_store.write_entry(
            session_id="web-console",
            turn_id="turn-stream-delta-only",
            entry_type=BrainTranscriptEntryType.WORKING_MEMORY_UPDATED,
            payload={"current_focus_summary": "delta only"},
            source="diagnostic_test",
            trace_id="stream-delta-only-trace",
        )
        message = websocket.receive_json()

    assert message["type"] == "transcript_event"
    assert message["event"]["trace_id"] == "stream-delta-only-trace"
    assert message["event"]["entry_type"] == BrainTranscriptEntryType.WORKING_MEMORY_UPDATED.value
