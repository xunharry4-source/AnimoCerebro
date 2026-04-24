from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zentex.common.resilience import OperationResult, ResilienceErrorCode, ResilienceStatus

UTC = timezone.utc


def atomic_write_text(path: Union[str, Path], payload: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace a text file using a same-directory temporary file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def atomic_write_json(path: Union[str, Path], payload: Any) -> None:
    """Atomically write a JSON file."""
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
    )


def write_json_commit_set(
    root: Union[str, Path],
    files: dict[str, Any],
    *,
    marker_name: str = "commit.json",
    marker_payload: dict[str, Optional[Any]] = None,
) -> None:
    """Write a logical file-set and publish it by atomically writing the commit marker last."""
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    marker_path = root_path / marker_name
    if marker_path.exists():
        marker_path.unlink()

    for relative_path, payload in files.items():
        atomic_write_json(root_path / relative_path, payload)

    atomic_write_json(
        marker_path,
        {
            **dict(marker_payload or {}),
            "committed_at": datetime.now(UTC).isoformat(),
            "files": sorted(files.keys()),
        },
    )


def load_json_commit_set(
    root: Union[str, Path],
    *,
    marker_name: str = "commit.json",
    source: str = "atomic_io",
) -> OperationResult:
    """Load a committed JSON file-set and diagnose missing/incomplete commit state."""
    root_path = Path(root)
    marker_path = root_path / marker_name
    if not marker_path.exists():
        return OperationResult.failed(
            status=ResilienceStatus.stale,
            code=ResilienceErrorCode.STORAGE_NOT_COMMITTED,
            message="commit marker is missing",
            source=source,
            data={"root": str(root_path), "missing_files": [marker_name]},
        )

    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    committed_files = marker.get("files")
    if not isinstance(committed_files, list) or not committed_files:
        return OperationResult.failed(
            status=ResilienceStatus.stale,
            code=ResilienceErrorCode.STORAGE_NOT_COMMITTED,
            message="commit marker does not describe any committed files",
            source=source,
            data={"root": str(root_path), "marker": marker, "missing_files": []},
        )

    missing_files = [
        relative_path
        for relative_path in committed_files
        if not isinstance(relative_path, str) or not (root_path / relative_path).exists()
    ]
    if missing_files:
        return OperationResult.failed(
            status=ResilienceStatus.stale,
            code=ResilienceErrorCode.STORAGE_COMMIT_INCOMPLETE,
            message="commit marker references missing files",
            source=source,
            data={
                "root": str(root_path),
                "marker": marker,
                "missing_files": missing_files,
            },
        )

    payloads: dict[str, Any] = {}
    for relative_path in committed_files:
        payloads[relative_path] = json.loads((root_path / relative_path).read_text(encoding="utf-8"))

    return OperationResult.success(
        status=ResilienceStatus.completed,
        data={
            "root": str(root_path),
            "marker": marker,
            "files": payloads,
        },
        source=source,
    )
