from __future__ import annotations

from typing import Any


def _logical_id(item: dict[str, Any]) -> str:
    return str(item.get("task_id") or item.get("id") or "").strip()


def _executor_type(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    raw = (
        item.get("executor_type")
        or metadata.get("executor_type")
        or metadata.get("external_executor_type")
        or ""
    )
    executor = str(raw or "").strip()
    target_id = str(item.get("target_id") or metadata.get("target_id") or "").strip()
    if executor:
        return executor
    if str(item.get("task_scope") or "").strip().lower() == "internal":
        return "internal"
    if target_id.startswith("cli:"):
        return "cli"
    if target_id.startswith("mcp:"):
        return "mcp"
    if target_id.startswith("agent:"):
        return "agent"
    if target_id.startswith("external_connector:"):
        return "external_connector"
    return "unknown"


def build_mixed_executor_orchestration_plan(task_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the mixed-executor execution graph and evidence handoff plan from Q8 task rows."""
    by_id = {_logical_id(item): item for item in task_rows if _logical_id(item)}
    executor_by_id = {task_id: _executor_type(item) for task_id, item in by_id.items()}
    dependency_edges: list[dict[str, str]] = []
    evidence_handover: list[dict[str, Any]] = []
    parallel_groups: dict[str, list[str]] = {}

    for task_id, item in by_id.items():
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        depends_on = item.get("depends_on") or metadata.get("depends_on") or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        for upstream in [str(dep).strip() for dep in depends_on if str(dep).strip()]:
            if upstream not in by_id:
                continue
            dependency_edges.append(
                {
                    "from": upstream,
                    "to": task_id,
                    "reason": f"{executor_by_id[task_id]} consumes {executor_by_id[upstream]} evidence",
                }
            )
            evidence_handover.append(
                {
                    "from_task": upstream,
                    "to_task": task_id,
                    "from_executor": executor_by_id[upstream],
                    "to_executor": executor_by_id[task_id],
                    "required_fields": ["task_id", "evidence_ref", "evidence_fingerprint"],
                }
            )
        group = str(metadata.get("parallel_group") or "").strip()
        if group:
            parallel_groups.setdefault(group, []).append(task_id)

    coverage = sorted(set(executor_by_id.values()))
    return {
        "status": "succeeded",
        "executor_coverage": coverage,
        "dependency_edges": dependency_edges,
        "parallel_groups": parallel_groups,
        "evidence_handover": evidence_handover,
        "orchestration_reason": (
            "internal and CLI are serial because CLI consumes local evidence; MCP and Agent are parallel after CLI "
            "because both consume the report independently; connector is last because it persists all upstream ids "
            "and evidence fingerprints."
        ),
        "bottleneck_candidates": ["mcp", "external_connector"],
        "proactive_monitor_task": {
            "task_id": "mixed-cross-executor-monitor",
            "title": "Monitor cross-executor evidence handoff completeness",
            "task_scope": "internal",
            "metadata": {
                "source_signal": "mixed_executor_orchestration",
                "suggestion": "verify every executor emits task_id, evidence_ref and evidence_fingerprint before connector aggregation",
                "worker_dispatch_enabled": False,
            },
        },
    }
