from __future__ import annotations

import re
from typing import Any


def build_q3_capability_inventory(
    *,
    cli_service: Any = None,
    mcp_service: Any = None,
    agent_service: Any = None,
    connector_service: Any = None,
) -> dict[str, Any]:
    """Build a Q3-style capability inventory from the live integration registries."""

    candidates: list[dict[str, Any]] = []
    candidates.extend(_cli_candidates(cli_service))
    candidates.extend(_mcp_candidates(mcp_service))
    candidates.extend(_agent_candidates(agent_service))
    candidates.extend(_connector_candidates(connector_service))

    capability_registry = {item["target_id"]: item for item in candidates}
    available_execution_tools = [
        item["target_id"]
        for item in candidates
        if item.get("healthy") is True and str(item.get("status") or "").lower() in {"active", "online", "healthy", "idle"}
    ]
    return {
        "available_execution_tools": available_execution_tools,
        "capability_registry": capability_registry,
        "candidate_capabilities": candidates,
        "registry_source": "live_external_capability_registries",
        "registry_counts": {
            "total": len(candidates),
            "available": len(available_execution_tools),
        },
    }


def build_q4_action_mapping(
    q3_inventory: dict[str, Any],
    *,
    objective: str = "",
    preferred_target_id: str = "",
    health_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Map Q3 registry inventory into executable Q4 actions with selection rationale."""

    candidates = _candidate_rows(q3_inventory, health_overrides=health_overrides or {})
    scored = [_score_candidate(item, objective=objective, preferred_target_id=preferred_target_id) for item in candidates]
    scored.sort(key=lambda item: (-float(item["score"]), str(item["target_id"])))
    selected = next((item for item in scored if item["eligible"] is True), None)
    action_name = _action_name(selected["target_id"]) if selected else ""

    non_selected = [
        {
            "target_id": item["target_id"],
            "score": item["score"],
            "reason": _non_selection_reason(item, selected),
        }
        for item in scored
        if selected is None or item["target_id"] != selected["target_id"]
    ]
    degraded = [item for item in scored if item["eligible"] is not True]
    proactive_actions = [
        {
            "task_id": f"recover-{_slug(item['target_id'])}",
            "title": f"Recover degraded capability {item['target_id']}",
            "task_scope": "internal",
            "metadata": {
                "source_signal": "capability_health_degraded",
                "target_id": item["target_id"],
                "suggestion": "rerun health check, re-register the capability, or switch to an authorized healthy replacement",
                "suggestion_only": True,
            },
        }
        for item in degraded
    ]
    return {
        "action_candidates": [action_name] if action_name else [],
        "capability_action_mapping": ({action_name: selected["target_id"]} if selected and action_name else {}),
        "selected_target_id": selected["target_id"] if selected else "",
        "selection_status": "selected" if selected else "blocked",
        "selection_rationale": {
            "objective": objective,
            "selected_target_id": selected["target_id"] if selected else "",
            "selected_reason": _selected_reason(selected) if selected else "no healthy registered capability matched the objective",
            "candidate_comparison": scored,
            "non_selected_candidates": non_selected,
            "no_alternative_reason": "" if non_selected else "no other registered candidate was available for comparison",
        },
        "proactive_actions": proactive_actions,
    }


def _cli_candidates(cli_service: Any) -> list[dict[str, Any]]:
    if cli_service is None:
        return []
    rows: list[dict[str, Any]] = []
    registry_store = getattr(cli_service, "_registry_store", None)
    registry_rows = {}
    if callable(getattr(registry_store, "list_current", None)):
        registry_rows = {row["asset_id"]: row for row in registry_store.list_current("cli")}
    runtime_states = {}
    if callable(getattr(cli_service, "list_tools", None)):
        runtime_states = {state.command_name: state for state in cli_service.list_tools()}
    for tool_name in sorted(set(registry_rows) | set(runtime_states)):
        state = runtime_states.get(tool_name)
        registry_row = registry_rows.get(tool_name) or {}
        health = _call_or_empty(cli_service, "get_tool_health", tool_name)
        status = str(health.get("status") or registry_row.get("status") or getattr(state, "status", "") or "").lower()
        healthy = bool(health.get("healthy", status == "active"))
        rows.append(
            {
                "target_id": f"cli:{tool_name}",
                "kind": "cli",
                "asset_id": tool_name,
                "display_name": registry_row.get("display_name") or tool_name,
                "status": status,
                "healthy": healthy,
                "health": health,
                "description": getattr(state, "description", "") if state is not None else (registry_row.get("payload") or {}).get("description", ""),
                "execution_domain": getattr(state, "execution_domain", None) if state is not None else (registry_row.get("payload") or {}).get("execution_domain"),
                "registry_seen": bool(registry_row),
                "runtime_seen": bool(state),
            }
        )
    return rows


def _mcp_candidates(mcp_service: Any) -> list[dict[str, Any]]:
    if mcp_service is None or not callable(getattr(mcp_service, "list_servers", None)):
        return []
    rows: list[dict[str, Any]] = []
    for server in mcp_service.list_servers():
        server_id = str(getattr(server, "server_id", "") or "")
        health = _call_or_empty(mcp_service, "get_server_health", server_id)
        status = str(health.get("status") or getattr(server, "status", "") or "").lower()
        healthy = status in {"online", "healthy", "ok"} and bool(health.get("healthy", True))
        for tool in getattr(server, "tools", []) or []:
            tool_name = str(getattr(tool, "tool_name", "") or "")
            rows.append(
                {
                    "target_id": f"mcp:{server_id}:{tool_name}",
                    "kind": "mcp",
                    "asset_id": server_id,
                    "capability": tool_name,
                    "status": status,
                    "healthy": healthy,
                    "health": health,
                    "registry_seen": True,
                    "runtime_seen": True,
                }
            )
    return rows


def _agent_candidates(agent_service: Any) -> list[dict[str, Any]]:
    manager = getattr(agent_service, "manager", None)
    if manager is None or not callable(getattr(manager, "list_assets", None)):
        return []
    rows: list[dict[str, Any]] = []
    for asset in manager.list_assets():
        status = str(getattr(getattr(asset, "status", ""), "value", getattr(asset, "status", "")) or "").lower()
        rows.append(
            {
                "target_id": f"agent:{asset.agent_id}",
                "kind": "agent",
                "asset_id": asset.agent_id,
                "status": status,
                "healthy": status in {"active", "idle"},
                "description": getattr(asset, "function_description", ""),
                "registry_seen": True,
                "runtime_seen": True,
            }
        )
    return rows


def _connector_candidates(connector_service: Any) -> list[dict[str, Any]]:
    if connector_service is None or not callable(getattr(connector_service, "list_connectors", None)):
        return []
    rows: list[dict[str, Any]] = []
    for connector in connector_service.list_connectors():
        status = str(getattr(getattr(connector, "status", ""), "value", getattr(connector, "status", "")) or "").lower()
        health = _call_or_empty(connector_service, "health_check", connector.connector_id)
        health_status = str(getattr(getattr(health, "health_status", ""), "value", getattr(health, "health_status", "")) or "").lower()
        for capability in getattr(connector, "capabilities", []) or []:
            rows.append(
                {
                    "target_id": f"external_connector:{connector.connector_id}",
                    "kind": "external_connector",
                    "asset_id": connector.connector_id,
                    "capability": capability.name,
                    "status": status,
                    "healthy": status == "active" and health_status == "healthy",
                    "health": health.model_dump(mode="json") if hasattr(health, "model_dump") else {},
                    "registry_seen": True,
                    "runtime_seen": True,
                }
            )
    return rows


def _candidate_rows(q3_inventory: dict[str, Any], *, health_overrides: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in q3_inventory.get("candidate_capabilities", []) if isinstance(item, dict)]
    if not rows:
        registry = q3_inventory.get("capability_registry") if isinstance(q3_inventory.get("capability_registry"), dict) else {}
        rows = [dict(value, target_id=target_id) for target_id, value in registry.items() if isinstance(value, dict)]
    for row in rows:
        override = health_overrides.get(str(row.get("target_id") or ""))
        if override:
            row.update(override)
    return rows


def _score_candidate(item: dict[str, Any], *, objective: str, preferred_target_id: str) -> dict[str, Any]:
    target_id = str(item.get("target_id") or "")
    status = str(item.get("status") or "").lower()
    healthy = item.get("healthy") is True and status in {"active", "online", "healthy", "idle"}
    objective_text = objective.lower()
    score = 0.0
    reasons: list[str] = []
    if healthy:
        score += 0.5
        reasons.append("health is active")
    else:
        reasons.append(f"health is not dispatchable: status={status or 'unknown'}")
    if preferred_target_id and target_id == preferred_target_id:
        score += 0.25
        reasons.append("matches preferred target from objective")
    if str(item.get("asset_id") or "").lower() in objective_text or target_id.lower() in objective_text:
        score += 0.15
        reasons.append("objective names this capability")
    if item.get("kind") == "cli":
        score += 0.1
        reasons.append("CLI executor matches requested external tool action")
    return {
        **item,
        "eligible": healthy,
        "score": round(score, 3),
        "score_reasons": reasons,
    }


def _selected_reason(selected: dict[str, Any]) -> str:
    return "selected because " + "; ".join(selected.get("score_reasons") or ["it is the highest scoring healthy candidate"])


def _non_selection_reason(item: dict[str, Any], selected: dict[str, Any] | None) -> str:
    if item.get("eligible") is not True:
        return "not selected because health/status is not dispatchable"
    if selected is None:
        return "not selected because no candidate passed selection"
    if float(item.get("score") or 0) < float(selected.get("score") or 0):
        return f"not selected because score {item.get('score')} is below selected score {selected.get('score')}"
    return "not selected because selected candidate has deterministic target-id precedence"


def _action_name(target_id: str) -> str:
    return f"run_{_slug(target_id)}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "capability"


def _call_or_empty(service: Any, method_name: str, *args: Any) -> dict[str, Any]:
    method = getattr(service, method_name, None)
    if not callable(method):
        return {}
    try:
        value = method(*args)
    except Exception as exc:
        return {"status": "unavailable", "healthy": False, "error": str(exc)}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value) if isinstance(value, dict) else {}
