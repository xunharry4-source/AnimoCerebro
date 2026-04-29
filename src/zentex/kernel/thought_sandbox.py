from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from plugins.simulation.thought.thought_sandbox_plugin import build_default_thought_sandbox
from zentex.kernel.state_domain import TranscriptEntry, TranscriptEntryType
from zentex.plugins.contracts import PluginLifecycleStatus
from zentex.plugins.simulation import SimulationIntent


UTC = timezone.utc
DESTRUCTIVE_TERMS = {
    "delete",
    "delete_file",
    "rm",
    "remove",
    "drop",
    "truncate",
    "overwrite",
    "format",
    "disable",
    "deploy",
    "execute_command",
    "identity",
    "self_modify",
}


def run_thought_sandbox_simulation(
    kernel: Any,
    *,
    session_id: str,
    action_type: str,
    action_payload: dict[str, Any],
    risk_level: str = "medium",
    task_type: str = "general",
    domain: str = "general",
    branches: Optional[list[dict[str, Any]]] = None,
    catastrophe_threshold: float = 0.7,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not session_id:
        raise ValueError("session_id is required")
    if not action_type:
        raise ValueError("action_type is required")
    if not isinstance(action_payload, dict) or not action_payload:
        raise ValueError("action_payload must be a non-empty dict")
    if catastrophe_threshold <= 0 or catastrophe_threshold > 1:
        raise ValueError("catastrophe_threshold must be within (0, 1]")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")

    scenario_id = f"g9-scenario-{uuid4().hex}"
    outcome_id = f"g9-outcome-{uuid4().hex}"
    branch_inputs = list(branches or [{"branch_id": "primary", "action_payload": action_payload}])
    selected_plugin = _select_simulation_plugin(kernel, domain=domain)
    plugin_failure: dict[str, Any] | None = None
    fallback_used = selected_plugin is None

    try:
        if selected_plugin is None:
            plugin_result = _run_default_rule_sandbox(
                action_type=action_type,
                action_payload=action_payload,
                risk_level=risk_level,
                task_type=task_type,
                domain=domain,
                branches=branch_inputs,
            )
            selected_plugin_id = "g9_default_rule_sandbox"
        else:
            selected_plugin_id = str(getattr(selected_plugin, "plugin_id", "unknown-simulation-plugin"))
            intent = SimulationIntent(
                intent_name=action_type,
                target_domain=domain,
                intent_payload={
                    **action_payload,
                    "task_type": task_type,
                    "branches": branch_inputs,
                },
                risk_level=risk_level,
            )
            plugin_result = selected_plugin.simulate_action(intent, dict(context or {}))
            plugin_result = _normalize_plugin_result(plugin_result, selected_plugin_id)
    except Exception as exc:
        plugin_failure = {
            "plugin_id": str(getattr(selected_plugin, "plugin_id", "unknown-simulation-plugin")),
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }
        fallback_used = True
        selected_plugin_id = "g9_default_rule_sandbox"
        plugin_result = _run_default_rule_sandbox(
            action_type=action_type,
            action_payload=action_payload,
            risk_level=risk_level,
            task_type=task_type,
            domain=domain,
            branches=branch_inputs,
        )

    rule_overlay = _catastrophe_overlay(
        action_type=action_type,
        action_payload=action_payload,
        risk_level=risk_level,
        base_risk=float(plugin_result["risk_score"]),
    )
    risk_score = max(float(plugin_result["risk_score"]), rule_overlay["risk_score"])
    catastrophe_predictions = list(dict.fromkeys([
        *list(plugin_result.get("catastrophe_predictions") or []),
        *rule_overlay["catastrophe_predictions"],
    ]))
    vetoed = bool(plugin_result.get("vetoed")) or risk_score >= catastrophe_threshold
    veto_reason = plugin_result.get("veto_reason") or rule_overlay["veto_reason"]
    if vetoed and not veto_reason:
        veto_reason = f"catastrophe_threshold_exceeded:{risk_score:.2f}>={catastrophe_threshold:.2f}"
    replan_required = bool(plugin_result.get("replan_required")) or vetoed

    record = {
        "feature_code": "G9",
        "scenario": {
            "scenario_id": scenario_id,
            "session_id": session_id,
            "action_type": action_type,
            "action_payload": action_payload,
            "risk_level": risk_level,
            "task_type": task_type,
            "domain": domain,
            "branches": branch_inputs,
            "catastrophe_threshold": catastrophe_threshold,
        },
        "outcome_id": outcome_id,
        "selected_plugin": selected_plugin_id,
        "plugin_contract": {
            "family": "simulation",
            "required_method": "simulate_action",
            "selected_plugin": selected_plugin_id,
            "fallback_used": fallback_used,
            "plugin_failure": plugin_failure,
        },
        "fallback_used": fallback_used,
        "risk_score": round(risk_score, 4),
        "catastrophe_predictions": catastrophe_predictions,
        "vetoed": vetoed,
        "veto_reason": veto_reason,
        "replan_required": replan_required,
        "side_effect_committed": False,
        "recommended_action": "replan" if replan_required else "allow_to_safety_gate",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_refs": [],
    }
    memory_id = _persist_memory(kernel, record)
    if memory_id:
        record["evidence_refs"].append({"type": "memory", "memory_id": memory_id})
    _cache_record(kernel, "_thought_sandbox_outcomes", outcome_id, record)
    _append_transcript(state, record, "g9_thought_sandbox_simulated")
    return record


def query_thought_sandbox_outcome(
    kernel: Any,
    *,
    session_id: str,
    outcome_id: str,
) -> dict[str, Any]:
    if not session_id or not outcome_id:
        raise ValueError("session_id and outcome_id are required")
    state = kernel._get_state(session_id)
    if state is None:
        raise ValueError(f"Session state missing for: {session_id}")
    records = getattr(kernel, "_thought_sandbox_outcomes", {})
    record = records.get(outcome_id)
    if not record:
        raise KeyError(f"G9 thought sandbox outcome not found: {outcome_id}")
    if record["scenario"]["session_id"] != session_id:
        raise KeyError(f"G9 thought sandbox outcome not found for session: {outcome_id}")
    _append_transcript(state, record, "g9_thought_sandbox_queried")
    return {**record, "query_visible": True}


def _select_simulation_plugin(kernel: Any, *, domain: str) -> Any:
    engine = getattr(getattr(kernel, "_cognition_service", None), "simulation_engine", None)
    plugins = list(getattr(engine, "_simulation_plugins", []) or [])
    for plugin in plugins:
        if getattr(plugin, "lifecycle_status", None) != PluginLifecycleStatus.ACTIVE:
            continue
        supported = set(getattr(plugin, "supported_domains", []) or [])
        if domain in supported or "general" in supported:
            if callable(getattr(plugin, "simulate_action", None)):
                return plugin
    return None


def _run_default_rule_sandbox(
    *,
    action_type: str,
    action_payload: dict[str, Any],
    risk_level: str,
    task_type: str,
    domain: str,
    branches: list[dict[str, Any]],
) -> dict[str, Any]:
    sandbox = build_default_thought_sandbox().transition_to(PluginLifecycleStatus.ACTIVE)
    intent = SimulationIntent(
        intent_name=action_type,
        target_domain=domain if domain in sandbox.supported_domains else "general",
        intent_payload={
            **action_payload,
            "tools": action_payload.get("tools", []),
            "constraints": action_payload.get("constraints", []),
            "task_type": task_type,
            "branches": branches,
        },
        risk_level=risk_level,
    )
    result = sandbox.simulate_action(intent, {"side_effect_policy": "forbid"})
    normalized = _normalize_plugin_result(result, sandbox.plugin_id)
    normalized["fallback_used"] = True
    return normalized


def _normalize_plugin_result(result: Any, plugin_id: str) -> dict[str, Any]:
    data = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
    return {
        "selected_plugin": data.get("simulated_by") or plugin_id,
        "risk_score": float(data.get("risk_score") or 0.0),
        "catastrophe_predictions": list(data.get("predicted_impacts") or []),
        "vetoed": not bool(data.get("is_safe", True)),
        "veto_reason": data.get("veto_reason"),
        "replan_required": bool(data.get("replan_required")),
        "fallback_used": bool(data.get("fallback_used")),
    }


def _catastrophe_overlay(
    *,
    action_type: str,
    action_payload: dict[str, Any],
    risk_level: str,
    base_risk: float,
) -> dict[str, Any]:
    serialized = json.dumps({"action_type": action_type, "payload": action_payload}, ensure_ascii=False).lower()
    risk = base_risk
    predictions: list[str] = []
    veto_reason = None
    if any(term in serialized for term in DESTRUCTIVE_TERMS):
        risk = max(risk, 0.92 if risk_level in {"high", "critical"} else 0.74)
        predictions.append("catastrophic_data_or_identity_loss_possible")
        veto_reason = "destructive_or_identity_action_requires_replan_before_execution"
    if "network" in serialized and "isolation" in serialized:
        risk = max(risk, 0.88)
        predictions.append("mutually_exclusive_network_and_isolation_constraints")
        veto_reason = veto_reason or "conflicting_execution_constraints"
    return {"risk_score": risk, "catastrophe_predictions": predictions, "veto_reason": veto_reason}


def _persist_memory(kernel: Any, record: dict[str, Any]) -> str | None:
    memory_service = getattr(kernel, "_memory_service", None)
    if memory_service is None or not callable(getattr(memory_service, "remember", None)):
        return None
    memory = memory_service.remember(
        title=f"G9 thought sandbox outcome {record['outcome_id']}",
        summary=f"G9 sandbox risk={record['risk_score']} vetoed={record['vetoed']}",
        content=json.dumps(record, ensure_ascii=False, sort_keys=True),
        layer="procedural",
        source="g9_thought_sandbox",
        trace_id=record["outcome_id"],
        target_id=record["scenario"]["scenario_id"],
        tags=["G9", "thought_sandbox", "simulation", "vetoed" if record["vetoed"] else "allowed"],
        thought_sandbox_outcome=record,
    )
    return str(getattr(memory, "memory_id", "") or "") or None


def _cache_record(kernel: Any, attr: str, key: str, record: dict[str, Any]) -> None:
    if not hasattr(kernel, attr):
        setattr(kernel, attr, {})
    getattr(kernel, attr)[key] = record


def _append_transcript(state: Any, record: dict[str, Any], entry_type: str) -> None:
    state.transcript.append(
        TranscriptEntry(
            entry_type=TranscriptEntryType.state_change,
            session_id=record["scenario"]["session_id"],
            payload={"feature_code": "G9", "entry_type": entry_type, **record},
        )
    )
