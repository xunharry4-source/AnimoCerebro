from __future__ import annotations

from typing import Any


def derive_workflow_diagnosis(status: str, status_section: dict) -> tuple[str, str]:
    error_msg = str(status_section.get("error_message") or "")
    if status in {"ready", "completed"}:
        return "completed", "执行链路完成，结果已写入"
    if status == "degraded":
        return "state_committed", "结果已落盘（快照回退降级）"
    if status in {"failed"}:
        return "unknown_failure", error_msg or "执行失败"
    if status == "partial_failed":
        return "execution_incomplete", error_msg or "执行链路不完整"
    if status == "stale":
        return "state_committed", error_msg or "结果标记过期"
    return "not_started", "尚未开始执行"


def build_workflow_question_entry(
    *,
    question_id: str,
    question_title: str,
    record: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status_section = record.get("status") or {}
    modules = record.get("modules") or {}
    plugin_runs = record.get("plugin_runs") or []
    module_runs = (
        ((record.get("execution_diagnosis") or {}).get("module_runs"))
        if isinstance(record.get("execution_diagnosis"), dict)
        else []
    )
    module_runs = module_runs if isinstance(module_runs, list) else []
    upstream_dependencies = record.get("upstream_dependencies") or []
    recovery_plan = record.get("recovery_plan") or {}

    current_status = str(status_section.get("status") or "not_started")
    error_message = status_section.get("error_message")

    phase_statuses = [
        {"phase": mid, "status": str((md or {}).get("status", "not_started"))}
        for mid, md in modules.items()
        if isinstance(md, dict)
    ]

    events: list[dict] = []
    for run in module_runs:
        if not isinstance(run, dict):
            continue
        events.append({
            "timestamp": str(run.get("finished_at") or run.get("started_at") or ""),
            "phase": f"module:{run.get('module_id') or '?'}",
            "phase_status": str(run.get("status") or "not_started"),
            "message": str(run.get("source") or run.get("module_id") or "module"),
            "error_message": run.get("error_message"),
        })
    for run in plugin_runs:
        if not isinstance(run, dict):
            continue
        events.append({
            "timestamp": str(run.get("started_at") or ""),
            "phase": f"plugin:{run.get('feature_code') or run.get('plugin_id') or '?'}",
            "phase_status": str(run.get("status") or "not_attempted"),
            "message": str(run.get("output_summary") or f"plugin {run.get('plugin_id')}"),
            "error_message": run.get("error_message"),
        })

    diag_code, diag_msg = derive_workflow_diagnosis(current_status, status_section)
    question = {
        "question_id": question_id,
        "question_title": question_title,
        "current_status": current_status,
        "authenticity_status": str(record.get("authenticity_status") or current_status),
        "used_fallback": bool((record.get("execution_diagnosis") or {}).get("used_fallback")) if isinstance(record.get("execution_diagnosis"), dict) else False,
        "latest_trace_id": status_section.get("trace_id"),
        "last_event_at": status_section.get("committed_at") or status_section.get("timestamp"),
        "latest_error": error_message,
        "trace_count": 1 if current_status != "not_started" else 0,
        "diagnosis_code": diag_code,
        "diagnosis_message": diag_msg,
        "module_runs": module_runs,
        "plugin_runs": plugin_runs,
        "upstream_dependencies": upstream_dependencies,
        "recovery_plan": recovery_plan,
        "phase_statuses": phase_statuses,
        "events": events,
    }
    return question, events
