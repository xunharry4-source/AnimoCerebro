from __future__ import annotations

from typing import Any, Dict, List


def build_completion_envelope(
    *,
    task_id: str,
    run_id: str,
    attempt: Dict[str, Any],
    context: Dict[str, Any],
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result = attempt.get("result") if isinstance(attempt.get("result"), dict) else {}
    executor_type = str(attempt.get("executor_type") or context.get("executor_type") or "").strip()
    executor_id = _executor_id(executor_type=executor_type, context=context)
    capability = str(attempt.get("capability") or context.get("capability") or "").strip()
    evidence_ref = f"react_execution:{executor_type}:{task_id}:{run_id}"
    evidence_refs = _evidence_refs(evidence_ref=evidence_ref, observations=observations, result=result)
    succeeded = bool(result.get("succeeded", result.get("status") in {"success", "completed"}))

    external_execution = {
        "executor_type": executor_type,
        "executor_id": executor_id,
        "owner_ref": attempt.get("owner_ref") or context.get("owner_ref"),
        "capability": capability,
        "trace_id": attempt.get("trace_id") or context.get("trace_id"),
        "attempt_id": attempt.get("attempt_id"),
    }
    evidence = {
        "evidence_ref": evidence_ref,
        "react_run_id": run_id,
        "attempt_id": attempt.get("attempt_id"),
        "task_id": task_id,
        "executor_type": executor_type,
        "executor_id": executor_id,
        "observation_count": len(observations),
        "evidence_refs": evidence_refs,
    }
    actual_outcome = {
        "status": "success" if succeeded else "failed",
        "task_id": task_id,
        "executor_type": executor_type,
        "executor_id": executor_id,
        "owner_ref": attempt.get("owner_ref") or context.get("owner_ref"),
        "capability": capability,
        "duration_seconds": result.get("duration_seconds"),
        "output": result.get("output", result.get("result", result)),
        "output_summary": _output_summary(result),
        "evidence_refs": evidence_refs,
        "external_execution": external_execution,
        "evidence": evidence,
    }
    return {
        "actual_outcome": actual_outcome,
        "external_execution": external_execution,
        "evidence": evidence,
    }


def _executor_id(*, executor_type: str, context: Dict[str, Any]) -> str:
    dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
    if executor_type == "internal_plugin":
        return str(dispatch.get("plugin_id") or "").strip()
    if executor_type == "external_connector":
        return str(dispatch.get("connector_id") or "").strip()
    if executor_type == "cli":
        return str(dispatch.get("tool_name") or "").strip()
    if executor_type == "mcp":
        return str(dispatch.get("server_id") or dispatch.get("tool_name") or "").strip()
    if executor_type == "agent":
        return str(dispatch.get("agent_id") or "").strip()
    return ""


def _evidence_refs(*, evidence_ref: str, observations: List[Dict[str, Any]], result: Dict[str, Any]) -> List[str]:
    refs: List[str] = [evidence_ref]
    for source in (result, result.get("execution_evidence") if isinstance(result.get("execution_evidence"), dict) else {}):
        for key in ("evidence_ref", "response_evidence_path", "runtime_log_id", "audit_log_id"):
            value = source.get(key) if isinstance(source, dict) else None
            if value:
                refs.append(str(value))
    for observation in observations:
        for value in observation.get("evidence_refs") or []:
            if value:
                refs.append(str(value))
    return list(dict.fromkeys(refs))


def _output_summary(result: Dict[str, Any]) -> Any:
    summary = result.get("output_summary") or result.get("summary") or result.get("message")
    if summary:
        return summary
    output = result.get("output", result.get("result"))
    if output is None:
        return "Executor completed without a structured output summary."
    text = str(output)
    return text if len(text) <= 500 else f"{text[:497]}..."


__all__ = ["build_completion_envelope"]
