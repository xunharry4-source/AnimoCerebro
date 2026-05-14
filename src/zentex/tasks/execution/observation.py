from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from zentex.tasks.execution.persistence import utc_now


def observe_attempt(*, context: Dict[str, Any], attempt: Dict[str, Any], runtime: Dict[str, Any]) -> Dict[str, Any]:
    result = attempt.get("result") if isinstance(attempt.get("result"), dict) else {}
    evidence_refs: List[str] = []
    physical_artifacts: List[Dict[str, Any]] = []
    for path_value in _artifact_paths(result, context):
        snapshot = _file_snapshot(path_value)
        physical_artifacts.append(snapshot)
        if snapshot.get("exists"):
            evidence_refs.append(str(snapshot["path"]))
    task_service = runtime.get("task_service")
    outcome = None
    if task_service is not None and callable(getattr(task_service, "get_task_outcome", None)):
        outcome = task_service.get_task_outcome(str(context.get("task_id") or ""))
        if outcome:
            evidence_refs.append(f"task_outcome:{context.get('task_id')}")
    return {
        "observation_id": f"react-observation-{uuid4().hex}",
        "task_id": context.get("task_id"),
        "attempt_id": attempt.get("attempt_id"),
        "source": "executor_result",
        "observed_at": utc_now(),
        "payload": {
            "attempt_status": attempt.get("status"),
            "executor_result": result,
            "task_outcome": outcome,
        },
        "evidence_refs": evidence_refs,
        "physical_artifacts": physical_artifacts,
    }


def _artifact_paths(result: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    for source in (
        result.get("physical_artifacts"),
        result.get("artifacts"),
        result.get("response_evidence_path"),
        (context.get("dispatch") or {}).get("expected_physical_artifacts") if isinstance(context.get("dispatch"), dict) else None,
    ):
        if source is None:
            continue
        if isinstance(source, list):
            paths.extend(str(item) for item in source if str(item).strip())
        else:
            paths.append(str(source))
    return list(dict.fromkeys(paths))


def _file_snapshot(path_value: str) -> Dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.exists():
        return {"path": str(path), "exists": False, "is_file": False, "size_bytes": 0}
    stat = path.stat()
    return {"path": str(path), "exists": True, "is_file": path.is_file(), "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
