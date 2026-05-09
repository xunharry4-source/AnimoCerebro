from __future__ import annotations

from pathlib import Path

from zentex.learning.service import LearningService
from zentex.learning.engine import LEARNING_SESSION_ID
from zentex.learning.store import LearningStore


def test_learning_store_real(tmp_path: Path) -> None:
    """功能：验证 learning.service.store 返回 learning 自有存储而不是 TranscriptStore。"""
    service = LearningService(storage_root=tmp_path)
    store = service.store
    assert store is not None
    assert isinstance(store, LearningStore)
    assert getattr(store, "_session_id", "") == LEARNING_SESSION_ID
    assert callable(getattr(store, "write_entry", None))
    assert callable(getattr(store, "query_by_session", None))
    assert Path(getattr(store, "db_path")).name == "learning.sqlite3"
