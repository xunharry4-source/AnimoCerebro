from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DEFAULT_CONFIG_PATH = Path("config/storage.toml")


@dataclass(frozen=True)
class StoragePaths:
    data_root: Path
    session_db: Path
    transcript_dir: Path
    workspace_db: Path
    app_data_dir: Path
    runtime_data_dir: Path
    nine_questions_dir: Path
    core_db: Path
    mcp_audit_db: Path

    def ensure_base_dirs(self) -> None:
        for path in (
            self.data_root,
            self.session_db.parent,
            self.workspace_db.parent,
            self.app_data_dir,
            self.runtime_data_dir,
            self.nine_questions_dir,
            self.core_db.parent,
            self.mcp_audit_db.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _read_storage_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    storage = payload.get("storage")
    return storage if isinstance(storage, dict) else {}


def _resolve_path(raw: Any, *, data_root: Path, fallback: str) -> Path:
    value = str(raw or fallback).strip()
    path = Path(value)
    if path.is_absolute():
        return path
    return path


def get_storage_paths(config_path: Path | str = _DEFAULT_CONFIG_PATH) -> StoragePaths:
    config = _read_storage_config(Path(config_path))
    env_root = os.environ.get("ZENTEX_DATA_ROOT")
    data_root = Path(str(env_root or config.get("data_root") or "data").strip())
    use_env_root_defaults = bool(env_root)

    def _configured_or_default(key: str, default_suffix: str) -> str:
        if use_env_root_defaults:
            return str(data_root / default_suffix)
        return str(config.get(key) or data_root / default_suffix)

    paths = StoragePaths(
        data_root=data_root,
        session_db=_resolve_path(_configured_or_default("session_db", "sessions.db"), data_root=data_root, fallback=str(data_root / "sessions.db")),
        transcript_dir=_resolve_path(
            os.environ.get("ZENTEX_TRANSCRIPT_DIR") or _configured_or_default("transcript_dir", "transcripts"),
            data_root=data_root,
            fallback=str(data_root / "transcripts"),
        ),
        workspace_db=_resolve_path(_configured_or_default("workspace_db", "workspaces.db"), data_root=data_root, fallback=str(data_root / "workspaces.db")),
        app_data_dir=_resolve_path(_configured_or_default("app_data_dir", "app_data"), data_root=data_root, fallback=str(data_root / "app_data")),
        runtime_data_dir=_resolve_path(_configured_or_default("runtime_data_dir", "runtime"), data_root=data_root, fallback=str(data_root / "runtime")),
        nine_questions_dir=_resolve_path(
            _configured_or_default("nine_questions_dir", "runtime/nine_questions"),
            data_root=data_root,
            fallback=str(data_root / "runtime/nine_questions"),
        ),
        core_db=_resolve_path(_configured_or_default("core_db", "runtime/zentex_core.db"), data_root=data_root, fallback=str(data_root / "runtime/zentex_core.db")),
        mcp_audit_db=_resolve_path(
            _configured_or_default("mcp_audit_db", "mcp_audit.sqlite3"),
            data_root=data_root,
            fallback=str(data_root / "mcp_audit.sqlite3"),
        ),
    )
    paths.ensure_base_dirs()
    return paths
