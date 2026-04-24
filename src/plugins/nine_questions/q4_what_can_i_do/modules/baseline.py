from __future__ import annotations

import re
from typing import Any


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def contains_write_like_action(action: str) -> bool:
    lowered = action.lower()
    if re.search(r"\brm\b", lowered):
        return True
    write_markers = (
        "write",
        "delete",
        "remove",
        "modify",
        "edit",
        "overwrite",
        "deploy",
        "apply",
        "chmod",
        "chown",
        "kill",
        "shutdown",
        "format",
        "drop",
    )
    return any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in write_markers)


def derive_permission_profile(snapshot: dict[str, Any], q3_inventory: dict[str, Any]) -> dict[str, Any]:
    permissions = snapshot.get("permissions")
    permissions = permissions if isinstance(permissions, dict) else {}
    workspace_permissions = snapshot.get("workspaces_and_permissions")
    workspace_permissions = workspace_permissions if isinstance(workspace_permissions, dict) else {}
    q3_permissions = q3_inventory.get("permissions")
    q3_permissions = q3_permissions if isinstance(q3_permissions, dict) else {}

    mode = normalize_text(q3_permissions.get("mode") or permissions.get("mode")) or "unknown"
    tenant_permissions = coerce_string_list(
        workspace_permissions.get("tenant_permissions") or permissions.get("tenant_scope")
    )
    execution_tokens = coerce_string_list(
        workspace_permissions.get("execution_tokens")
        or permissions.get("execution_tokens")
        or permissions.get("brain_scope")
    )
    workspace_zones = coerce_string_list(
        (q3_inventory.get("accessible_workspace_zones") if isinstance(q3_inventory, dict) else None)
        or workspace_permissions.get("available_workspaces")
        or permissions.get("accessible_workspace_zones")
    )
    return {
        "mode": mode,
        "tenant_permissions": tenant_permissions,
        "execution_tokens": execution_tokens,
        "accessible_workspace_zones": workspace_zones,
        "is_read_only": mode == "read_only" or not execution_tokens,
    }


def normalize_functional_capabilities(functional_capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in functional_capabilities:
        if not isinstance(item, dict) or item.get("status") != "done":
            continue
        normalized.append(
            {
                "plugin_id": normalize_text(item.get("plugin_id")),
                "status": normalize_text(item.get("status")) or "done",
                "result": item.get("result") if isinstance(item.get("result"), dict) else {},
            }
        )
    return normalized


def derive_capability_baseline(
    snapshot: dict[str, Any],
    q3_inventory: dict[str, Any],
    exec_domains: list[str],
    permission_profile: dict[str, Any],
    functional_capabilities: list[dict[str, Any]],
) -> dict[str, list[str]]:
    resource_evaluation = snapshot.get("q3_resource_evaluation")
    resource_evaluation = resource_evaluation if isinstance(resource_evaluation, dict) else {}
    cognitive_tools = coerce_string_list(q3_inventory.get("available_cognitive_tools"))
    connected_agents = q3_inventory.get("connected_agents")
    connected_agents = connected_agents if isinstance(connected_agents, list) else []
    workspace_zones = coerce_string_list(permission_profile.get("accessible_workspace_zones"))
    strategy_patches = coerce_string_list(q3_inventory.get("activated_strategy_patches"))

    capability_upper_limits: list[str] = []
    actionable_space: list[str] = []
    executable_strategies: list[str] = []

    if cognitive_tools:
        capability_upper_limits.append("analyze available workspace and runtime state")
        actionable_space.append("inspect workspace summaries")
        executable_strategies.append("static analysis")

    if workspace_zones:
        capability_upper_limits.append("operate within accessible workspace zones")
        actionable_space.append("inspect accessible workspace zones")

    if exec_domains:
        capability_upper_limits.append("invoke enabled execution domains")
        actionable_space.append("invoke enabled tool endpoints")
        executable_strategies.append("tool-assisted execution")
    else:
        executable_strategies.append("analysis-only planning")

    if connected_agents:
        capability_upper_limits.append("delegate work to connected agents")
        actionable_space.append("coordinate connected agents")
        executable_strategies.append("delegated collaboration")

    if strategy_patches:
        capability_upper_limits.append("apply active strategy patches")
        executable_strategies.append("strategy-patch-guided execution")

    for item in functional_capabilities:
        plugin_id = normalize_text(item.get("plugin_id"))
        if plugin_id:
            capability_upper_limits.append(f"use functional capability {plugin_id}")

    resource_status = normalize_text(resource_evaluation.get("resource_status"))
    if resource_status == "critically_lacking":
        executable_strategies.append("resource recovery before execution")
    elif resource_status == "degraded":
        executable_strategies.append("conservative degraded-mode execution")

    if permission_profile.get("is_read_only"):
        capability_upper_limits.append("perform read-only inspection")
        actionable_space = [
            item
            for item in actionable_space
            if not contains_write_like_action(item)
        ]
        executable_strategies = [
            item
            for item in executable_strategies
            if not contains_write_like_action(item)
        ]
        actionable_space.append("read logs and inspect snapshots")
        executable_strategies.append("request human confirmation before any write action")

    capability_upper_limits = list(dict.fromkeys(item for item in capability_upper_limits if normalize_text(item)))
    actionable_space = list(dict.fromkeys(item for item in actionable_space if normalize_text(item)))
    executable_strategies = list(dict.fromkeys(item for item in executable_strategies if normalize_text(item)))

    return {
        "capability_upper_limits": capability_upper_limits,
        "actionable_space": actionable_space,
        "executable_strategies": executable_strategies,
    }


def merge_with_capability_baseline(
    inferred: list[str],
    baseline: list[str],
    *,
    read_only: bool,
) -> list[str]:
    merged = list(dict.fromkeys(coerce_string_list(inferred) + coerce_string_list(baseline)))
    if read_only:
        merged = [item for item in merged if not contains_write_like_action(item)]
    return merged
