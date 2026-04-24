from __future__ import annotations

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


def normalize_functional_authorization_inputs(
    functional_authorization_inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in functional_authorization_inputs:
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


def resolve_q3_connected_agents(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    connected_agents = snapshot.get("q3_connected_agents")
    if isinstance(connected_agents, list):
        return [item for item in connected_agents if isinstance(item, dict)]

    q3_inventory = snapshot.get("q3_unified_asset_inventory")
    if isinstance(q3_inventory, dict) and isinstance(q3_inventory.get("connected_agents"), list):
        return [item for item in q3_inventory.get("connected_agents", []) if isinstance(item, dict)]

    connected_agents_inventory = snapshot.get("connected_agents_inventory")
    if isinstance(connected_agents_inventory, dict) and isinstance(connected_agents_inventory.get("connected_agents"), list):
        return [item for item in connected_agents_inventory.get("connected_agents", []) if isinstance(item, dict)]

    return []


def resolve_agent_trust_policy(snapshot: dict[str, Any]) -> dict[str, str]:
    trust_policy = snapshot.get("agent_trust_policy")
    if isinstance(trust_policy, dict):
        return {
            str(key): str(value)
            for key, value in trust_policy.items()
            if normalize_text(key) and normalize_text(value)
        }
    return {}


def resolve_contact_policy(snapshot: dict[str, Any]) -> dict[str, Any]:
    contact_policy = snapshot.get("contact_policy")
    if isinstance(contact_policy, dict):
        return contact_policy

    q4_permission_profile = snapshot.get("q4_permission_profile")
    q4_permission_profile = q4_permission_profile if isinstance(q4_permission_profile, dict) else {}
    if not q4_permission_profile:
        return {}

    policy: dict[str, Any] = {
        "interaction_scope": normalize_text(q4_permission_profile.get("mode")) or "unknown",
        "requires_human_confirmation": bool(q4_permission_profile.get("is_read_only")),
        "requires_cloud_audit": False,
    }
    execution_tokens = coerce_string_list(q4_permission_profile.get("execution_tokens"))
    if execution_tokens:
        policy["execution_tokens"] = execution_tokens
    accessible_workspace_zones = coerce_string_list(q4_permission_profile.get("accessible_workspace_zones"))
    if accessible_workspace_zones:
        policy["accessible_workspace_zones"] = accessible_workspace_zones
    return policy


def resolve_tenant_scope(snapshot: dict[str, Any]) -> dict[str, Any]:
    tenant_scope = snapshot.get("tenant_scope")
    if isinstance(tenant_scope, dict):
        return tenant_scope

    q4_permission_profile = snapshot.get("q4_permission_profile")
    q4_permission_profile = q4_permission_profile if isinstance(q4_permission_profile, dict) else {}
    if not q4_permission_profile:
        return {}

    derived_scope: dict[str, Any] = {}
    tenant_permissions = coerce_string_list(q4_permission_profile.get("tenant_permissions"))
    if tenant_permissions:
        derived_scope["tenant_permissions"] = tenant_permissions
        derived_scope["same_org_only"] = True
    workspace_zones = coerce_string_list(q4_permission_profile.get("accessible_workspace_zones"))
    if workspace_zones:
        derived_scope["accessible_workspace_zones"] = workspace_zones
    return derived_scope


def derive_agent_trust_status(snapshot: dict[str, Any]) -> dict[str, str]:
    trust_policy = resolve_agent_trust_policy(snapshot)
    if trust_policy:
        return trust_policy

    connected_agents = resolve_q3_connected_agents(snapshot)
    derived: dict[str, str] = {}
    for agent in connected_agents:
        if not isinstance(agent, dict):
            continue
        agent_id = normalize_text(agent.get("agent_id") or agent.get("id") or agent.get("name"))
        trust = normalize_text(agent.get("trust_level") or agent.get("status") or agent.get("scope"))
        if agent_id and trust:
            derived[agent_id] = trust
    return derived


def derive_authorization_baseline(
    snapshot: dict[str, Any],
    actionable_space: list[str],
    normalized_functional_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    permission_profile = snapshot.get("q4_permission_profile")
    permission_profile = permission_profile if isinstance(permission_profile, dict) else {}
    contact_policy = resolve_contact_policy(snapshot)
    tenant_scope = resolve_tenant_scope(snapshot)
    trust_status = derive_agent_trust_status(snapshot)

    mode = normalize_text(permission_profile.get("mode")) or "unknown"
    requires_human_confirmation = bool(permission_profile.get("is_read_only"))
    requires_cloud_audit = False

    allowed_action_space: list[str] = []
    forbidden_action_space: list[dict[str, str]] = []
    requires_escalation_actions: list[str] = []
    contact_and_org_boundaries: dict[str, Any] = {
        "execution_tier": "constrained_execute",
        "interaction_scope": "whitelist_only",
        "requires_human_confirmation": requires_human_confirmation,
        "requires_cloud_audit": requires_cloud_audit,
    }

    if mode == "read_only":
        contact_and_org_boundaries["execution_tier"] = "read_only"
        allowed_action_space = [
            action for action in actionable_space if "read" in action.lower() or "inspect" in action.lower()
        ]
        for action in actionable_space:
            if action not in allowed_action_space:
                forbidden_action_space.append({"action": action, "reason": "read_only boundary"})
                requires_escalation_actions.append(action)
    else:
        allowed_action_space = list(actionable_space)

    if tenant_scope:
        contact_and_org_boundaries["tenant_scope"] = tenant_scope
        if tenant_scope.get("same_org_only") is True:
            contact_and_org_boundaries["interaction_scope"] = "same_org_only"
        if isinstance(tenant_scope.get("forbidden_actions"), list):
            forbidden_set = {normalize_text(item) for item in tenant_scope.get("forbidden_actions") if normalize_text(item)}
            retained_allowed: list[str] = []
            for action in allowed_action_space:
                if action in forbidden_set:
                    forbidden_action_space.append({"action": action, "reason": "tenant scope forbidden"})
                else:
                    retained_allowed.append(action)
            allowed_action_space = retained_allowed

    if contact_policy:
        contact_and_org_boundaries["contact_policy"] = contact_policy
        if contact_policy.get("requires_human_confirmation") is True:
            requires_human_confirmation = True
            contact_and_org_boundaries["requires_human_confirmation"] = True
        if contact_policy.get("requires_cloud_audit") is True:
            requires_cloud_audit = True
            contact_and_org_boundaries["requires_cloud_audit"] = True
        blocked_contacts = coerce_string_list(contact_policy.get("blocked_actions"))
        if blocked_contacts:
            retained_allowed = []
            blocked_set = set(blocked_contacts)
            for action in allowed_action_space:
                if action in blocked_set:
                    forbidden_action_space.append({"action": action, "reason": "contact policy blocked"})
                else:
                    retained_allowed.append(action)
            allowed_action_space = retained_allowed

    if trust_status:
        contact_and_org_boundaries["agent_trust_status"] = trust_status
        if any(status.lower() in {"pending", "revoked", "blocked"} for status in trust_status.values()):
            requires_human_confirmation = True
            contact_and_org_boundaries["requires_human_confirmation"] = True

    for item in normalized_functional_inputs:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if not result:
            continue
        if isinstance(result.get("forbidden_actions"), list):
            for action in result.get("forbidden_actions", []):
                text = normalize_text(action)
                if text:
                    forbidden_action_space.append({"action": text, "reason": f"functional policy {item.get('plugin_id')}"})
        if isinstance(result.get("requires_escalation_actions"), list):
            requires_escalation_actions.extend(coerce_string_list(result.get("requires_escalation_actions")))

    forbidden_index = {
        (normalize_text(item.get("action")), normalize_text(item.get("reason"))): item
        for item in forbidden_action_space
        if normalize_text(item.get("action"))
    }
    forbidden_action_space = list(forbidden_index.values())
    requires_escalation_actions = list(
        dict.fromkeys(action for action in requires_escalation_actions if normalize_text(action))
    )
    allowed_action_space = [
        action
        for action in list(dict.fromkeys(actionable for actionable in allowed_action_space if normalize_text(actionable)))
        if action not in {item["action"] for item in forbidden_action_space}
    ]

    return {
        "allowed_action_space": allowed_action_space,
        "forbidden_action_space": forbidden_action_space,
        "contact_and_org_boundaries": contact_and_org_boundaries,
        "requires_escalation_actions": requires_escalation_actions,
        "agent_trust_status": trust_status,
    }
