from __future__ import annotations

"""Workspace access policy for runtime analysis features."""

import os
import tomllib
from pathlib import Path
from typing import Any

from zentex.common.storage_paths import get_storage_paths

_CONFIG_PATH = Path("config/storage.toml")
_DEFAULT_Q1_ANALYSIS_DIR = "~/.zentex/q1_analysis_workspace"


def _read_workspace_config(config_path: Path = _CONFIG_PATH) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    workspace = payload.get("workspace")
    return workspace if isinstance(workspace, dict) else {}


def _resolve_configured_path(raw: Any, fallback: str) -> Path:
    value = str(raw or fallback).strip() or fallback
    return Path(value).expanduser().resolve()


def get_q1_default_analysis_workspace() -> Path:
    config = _read_workspace_config()
    raw = (
        os.environ.get("ZENTEX_Q1_WORKSPACE_ROOT")
        or config.get("q1_default_analysis_dir")
        or config.get("default_analysis_dir")
        or _DEFAULT_Q1_ANALYSIS_DIR
    )
    path = _resolve_configured_path(raw, _DEFAULT_Q1_ANALYSIS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def get_configured_workspace_roots(workspace_store: Any = None) -> list[Path]:
    roots: list[Path] = [get_q1_default_analysis_workspace()]
    store = workspace_store
    close_store = False
    if store is None:
        from zentex.kernel.workspace_store import WorkspaceStore

        store = WorkspaceStore(get_storage_paths().workspace_db)
        close_store = True
    try:
        for workspace in store.list_workspaces():
            path = Path(str(getattr(workspace, "path", ""))).expanduser().resolve()
            if path.exists() and path.is_dir():
                roots.append(path)
    finally:
        if close_store:
            store.close()

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            deduped.append(root)
    return deduped


def _resolve_workspace_store_default_root(store: Any) -> Path | None:
    if store is None:
        return None
    if not hasattr(store, "get_default_workspace"):
        return None
    try:
        workspace = store.get_default_workspace()
    except Exception:
        return None
    if workspace is None:
        return None

    path = Path(str(getattr(workspace, "path", ""))).expanduser().resolve()
    if path.exists() and path.is_dir():
        return path
    return None


def resolve_q1_workspace_root(candidate: Any = None, workspace_store: Any = None) -> Path:
    default_root = get_q1_default_analysis_workspace()
    if candidate in (None, ""):
        configured_default = _resolve_workspace_store_default_root(workspace_store)
        return configured_default or default_root

    try:
        requested = Path(str(candidate)).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return default_root

    if not requested.exists() or not requested.is_dir():
        return default_root

    allowed_roots = get_configured_workspace_roots(workspace_store)
    if any(requested == root or _is_relative_to(requested, root) for root in allowed_roots):
        return requested
    return default_root


def build_q1_workspace_policy_snapshot(workspace_root: Path, workspace_store: Any = None) -> dict[str, Any]:
    allowed_roots = get_configured_workspace_roots(workspace_store)
    return {
        "workspace_root": str(workspace_root),
        "default_analysis_workspace": str(get_q1_default_analysis_workspace()),
        "allowed_workspace_roots": [str(root) for root in allowed_roots],
        "access_policy": "q1_configured_analysis_workspace_or_console_workspaces_only",
    }
