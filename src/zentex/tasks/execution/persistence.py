from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_metadata(task: Dict[str, Any] | None) -> Dict[str, Any]:
    metadata = (task or {}).get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def append_graph_node_io(
    *,
    task_dao: Any,
    task_id: str,
    run_id: str,
    node_id: str,
    node_type: str,
    status: str,
    input_payload: Dict[str, Any] | None = None,
    output_payload: Dict[str, Any] | None = None,
    error: Dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
) -> None:
    if task_dao is None or not callable(getattr(task_dao, "get_task", None)):
        return
    task = task_dao.get_task(task_id)
    if task is None:
        return
    metadata = _task_metadata(task)
    react_execution = dict(metadata.get("react_execution") or {})
    graph_runs = list(react_execution.get("graph_runs") or [])
    graph_runs.append(
        {
            "run_id": run_id,
            "node_id": node_id,
            "node_label": node_id.replace("_", " ").title(),
            "node_type": node_type,
            "status": status,
            "started_at": utc_now(),
            "finished_at": utc_now(),
            "input": _json_safe(dict(input_payload or {})),
            "output": _json_safe(dict(output_payload or {})),
            "error": _json_safe(dict(error or {})) if error else None,
            "evidence_refs": _json_safe(list(evidence_refs or [])),
        }
    )
    react_execution.update(
        {
            "enabled": True,
            "run_id": run_id,
            "graph_runtime": "langgraph",
            "graph_runs": graph_runs,
        }
    )
    metadata["react_execution"] = react_execution
    task_dao.update_task(task_id, {"metadata": _json_safe(metadata)})


def mark_react_terminal(
    *,
    task_dao: Any,
    task_id: str,
    run_id: str,
    status: str,
    result: Dict[str, Any],
) -> None:
    task = task_dao.get_task(task_id) if task_dao is not None and callable(getattr(task_dao, "get_task", None)) else None
    if task is None:
        return
    metadata = _task_metadata(task)
    react_execution = dict(metadata.get("react_execution") or {})
    react_execution.update(
        {
            "enabled": True,
            "run_id": run_id,
            "graph_runtime": "langgraph",
            "terminal_status": status,
            "terminal_result": _json_safe(dict(result or {})),
            "finished_at": utc_now(),
        }
    )
    metadata["react_execution"] = react_execution
    task_dao.update_task(task_id, {"metadata": _json_safe(metadata)})
