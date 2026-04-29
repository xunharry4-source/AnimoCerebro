from __future__ import annotations

import gc
import threading
import warnings
from datetime import datetime, timezone

from zentex.common.database import DatabaseConnection
from zentex.environment.preference_models import UserPreference
from zentex.upgrade.ledger import UpgradeAuditStore, UpgradeMemoryStore
from zentex.web_console.contracts.kernel_service import SessionSnapshot
from zentex.web_console.models.workspace import WorkspaceConfig


def test_pydantic_v2_schema_examples_and_datetime_json_are_stable(tmp_path):
    timestamp = datetime(2026, 4, 29, 1, 2, 3, tzinfo=timezone.utc)

    session = SessionSnapshot(
        session_id="session-warning-cleanup",
        state_id="state-warning-cleanup",
        workspace=str(tmp_path),
        created_at=timestamp,
    )
    preference = UserPreference(
        preference_id="pref-warning-cleanup",
        content="keep ISO JSON serialization",
        confirmed_at=timestamp,
        source="focused_test",
    )

    assert session.model_dump(mode="json")["created_at"] == "2026-04-29T01:02:03Z"
    assert preference.model_dump(mode="json")["confirmed_at"] == "2026-04-29T01:02:03Z"
    assert SessionSnapshot.model_json_schema()["example"]["session_id"] == "sess-123"
    assert WorkspaceConfig.model_json_schema()["example"]["name"] == "Main Project"


def test_sqlite_resource_cleanup_closes_cross_thread_and_memory_connections(tmp_path):
    db = DatabaseConnection(str(tmp_path / "cleanup.sqlite3"))

    def use_connection_from_worker_thread() -> None:
        db.execute_update("CREATE TABLE IF NOT EXISTS cleanup_probe (id INTEGER PRIMARY KEY)")
        db.execute_update("INSERT INTO cleanup_probe DEFAULT VALUES")

    worker = threading.Thread(target=use_connection_from_worker_thread)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()

    audit_store = UpgradeAuditStore()
    memory_store = UpgradeMemoryStore()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        db.shutdown()
        audit_store.close()
        memory_store.close()
        del db, audit_store, memory_store
        gc.collect()

    leaked = [
        warning
        for warning in captured
        if issubclass(warning.category, ResourceWarning)
        and "unclosed database" in str(warning.message)
    ]
    assert leaked == []
