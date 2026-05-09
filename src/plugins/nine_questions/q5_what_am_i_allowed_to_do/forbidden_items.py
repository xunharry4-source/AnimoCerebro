from __future__ import annotations

import json
import re
from typing import Any

from plugins.nine_questions.q2_asset_inventory.service import (
    load_internal_public_output as load_q2_internal,
)
from zentex.safety.safety_gate import SafetyGate


def query_nine_question_forbidden_items(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return user-configured and system-owned forbidden items for Q5 prompts."""
    payload = context if isinstance(context, dict) else {}
    user_items, user_source = _query_user_forbidden_actions(payload)
    identity_constraints, identity_sources = _query_identity_constraints(payload)
    safety_redlines = _query_system_safety_redlines()
    safety_items = _dedupe(
        f"{item['action_type']}: {item['description']}"
        for item in safety_redlines
        if item.get("action_type") and item.get("description")
    )
    system_items = _dedupe([*identity_constraints, *safety_items])
    return {
        "user_forbidden_actions": user_items,
        "system_forbidden_actions": system_items,
        "system_identity_constraints": identity_constraints,
        "system_safety_redline_actions": safety_redlines,
        "combined_forbidden_actions": _dedupe([*user_items, *system_items]),
        "sources": {
            "user_settings": user_source,
            "system_identity_constraints": identity_sources,
            "system_safety_redlines": "zentex.safety.safety_gate.SafetyGate.DEFAULT_REDLINES",
        },
    }


def _query_user_forbidden_actions(context: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    workspace = _resolve_workspace_config(context)
    if workspace is not None:
        raw = _get_field(workspace, "forbidden_actions")
        return _parse_forbidden_text(raw), {
            "source": "workspace.forbidden_actions",
            "workspace_id": _get_field(workspace, "id"),
            "workspace_name": _get_field(workspace, "name"),
            "workspace_path": _get_field(workspace, "path"),
        }

    for key in ("workspace_forbidden_actions", "configured_forbidden_actions", "user_forbidden_actions"):
        if key in context:
            return _parse_forbidden_text(context.get(key)), {"source": f"context.{key}"}

    return [], {"source": "workspace.forbidden_actions", "workspace_found": False}


def _resolve_workspace_config(context: dict[str, Any]) -> Any:
    for key in ("workspace", "workspace_config", "current_workspace", "default_workspace"):
        workspace = context.get(key)
        if workspace is not None and _get_field(workspace, "forbidden_actions") is not None:
            return workspace

    store = context.get("workspace_store")
    if store is None:
        return None

    workspace_id = context.get("workspace_id")
    if workspace_id not in (None, "") and hasattr(store, "get_workspace"):
        workspace = store.get_workspace(int(workspace_id))
        if workspace is not None:
            return workspace

    workspace_path = context.get("workspace_path") or context.get("workspace_root")
    if workspace_path and hasattr(store, "get_workspace_by_path"):
        workspace = store.get_workspace_by_path(str(workspace_path))
        if workspace is not None:
            return workspace

    if hasattr(store, "get_default_workspace"):
        return store.get_default_workspace()
    return None


def _query_identity_constraints(context: dict[str, Any]) -> tuple[list[str], list[str]]:
    session_id = context.get("session_id", "nq-baseline")
    db_path = context.get("nine_question_state_db_path")
    try:
        q2_internal_output = load_q2_internal(session_id=session_id, db_path=db_path)
    except Exception:
        q2_internal_output = {}
    values = _string_list(_get_field(q2_internal_output, "non_bypassable_internal_constraints"))
    if not values:
        values = _string_list(_get_field(q2_internal_output, "non_bypassable_constraints"))
    sources = ["database.q2_snapshots.internal_asset_inventory"] if values else []
    return _dedupe(values), sources


def _query_system_safety_redlines() -> list[dict[str, Any]]:
    redlines: list[dict[str, Any]] = []
    for item in SafetyGate.DEFAULT_REDLINES:
        redlines.append(
            {
                "action_type": item.action_type,
                "category": item.category.value,
                "description": item.description,
                "non_bypassable_constraints": list(item.non_bypassable_constraints),
                "requires_dual_confirmation": item.requires_dual_confirmation,
                "requires_cloud_audit": item.requires_cloud_audit,
                "requires_human_review": item.requires_human_review,
            }
        )
    return redlines


def _parse_forbidden_text(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, list):
        return _dedupe(_string_list(raw))
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return _dedupe(_string_list(parsed))
    return _dedupe(_strip_list_marker(line) for line in text.splitlines() if line.strip())


def _strip_list_marker(value: str) -> str:
    return re.sub(r"^\s*(?:[-*]|\d+[.)）])\s*", "", value).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _get_field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _nested_get(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        current = _get_field(current, key)
        if current is None:
            return None
    return current
