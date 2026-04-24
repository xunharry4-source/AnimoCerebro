from __future__ import annotations

from pathlib import Path

from zentex.common.storage_paths import get_storage_paths


def test_storage_paths_exposes_mcp_audit_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ZENTEX_DATA_ROOT", str(tmp_path))

    paths = get_storage_paths()

    assert paths.mcp_audit_db == Path(tmp_path) / "mcp_audit.sqlite3"
