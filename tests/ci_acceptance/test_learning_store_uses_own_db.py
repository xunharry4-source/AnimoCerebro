from __future__ import annotations

from pathlib import Path

from zentex.learning.engine import LEARNING_SESSION_ID, get_learning_status
from zentex.learning.service import LearningService
from zentex.learning.store import LEARNING_EVENT_TYPE, LearningStore


def test_learning_service_uses_own_store_and_db(tmp_path: Path) -> None:
    service = LearningService(storage_root=tmp_path)

    assert isinstance(service.store, LearningStore)
    assert service.store.db_path == tmp_path / "learning.sqlite3"


def test_learning_store_persists_queryable_events(tmp_path: Path) -> None:
    service = LearningService(storage_root=tmp_path)
    service.store.write_entry(
        session_id=LEARNING_SESSION_ID,
        turn_id="cycle_test",
        entry_type=LEARNING_EVENT_TYPE,
        payload={"kind": "completed", "summary": "ok"},
        source="test",
        trace_id="trace-1",
    )

    entries = service.query_history_entries(limit=10)
    assert len(entries) == 1
    assert entries[0].trace_id == "trace-1"

    status = get_learning_status(service.store, limit=10)
    assert status["recent_events_count"] == 1
    assert status["recent_events"][0]["entry_type"] == LEARNING_EVENT_TYPE
