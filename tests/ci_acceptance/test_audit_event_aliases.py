from __future__ import annotations

from zentex.common.nine_questions_shared import require_audit_store, require_transcript_store
from zentex.kernel import (
    AuditEvent,
    AuditEventStore,
    AuditEventType,
    BrainTranscriptEntry,
    BrainTranscriptEntryType,
    BrainTranscriptStore,
)


def test_kernel_audit_aliases_map_to_legacy_exports() -> None:
    assert AuditEventStore is BrainTranscriptStore
    assert AuditEventType is BrainTranscriptEntryType
    assert AuditEvent is BrainTranscriptEntry


def test_require_audit_store_accepts_audit_store_key(tmp_path) -> None:
    store = AuditEventStore(tmp_path / "audit.sqlite3")
    try:
        assert require_audit_store({"audit_store": store}) is store
        assert require_transcript_store({"audit_store": store}) is store
    finally:
        store.close()
