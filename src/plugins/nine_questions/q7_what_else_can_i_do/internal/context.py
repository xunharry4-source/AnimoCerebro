from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _coerce_text_list(value: Any, *, limit: int = 20) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    elif value in (None, "", {}, []):
        raw_items = []
    else:
        raw_items = [value]
    normalized: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            text = "；".join(
                f"{key}: {val}"
                for key, val in item.items()
                if val not in (None, "", [], {})
            )
        else:
            text = str(item or "")
        text = text.strip()
        if text:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return list(dict.fromkeys(normalized))


def extract_identity_kernel(context: dict[str, Any], upstream_context: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "identity_kernel_snapshot",
        "identity_kernel",
        "q3_identity_kernel_snapshot",
        "q3_identity_kernel",
        "q2_identity_kernel_snapshot",
        "q2_identity_kernel",
    ):
        identity = upstream_context.get(key)
        if isinstance(identity, dict) and identity:
            return identity
    q3_role_profile = upstream_context.get("q3_role_profile")
    if isinstance(q3_role_profile, dict):
        identity = q3_role_profile.get("identity_kernel_snapshot") or q3_role_profile.get("identity_kernel")
        if isinstance(identity, dict) and identity:
            return identity
    state_identity = context.get("identity_kernel_snapshot") or context.get("identity_kernel")
    if isinstance(state_identity, dict) and state_identity:
        return state_identity
    store = context.get("system_identity_store")
    get_identity = getattr(store, "get_identity", None)
    if callable(get_identity):
        payload = get_identity()
        if isinstance(payload, dict):
            snapshot = payload.get("identity_kernel_snapshot")
            if isinstance(snapshot, dict) and snapshot:
                return snapshot
            return payload
    return {}


def extract_current_intent_context(context: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "current_intent_context",
        "current_user_intent",
        "user_intent",
        "objective",
        "current_objective",
        "task_request",
        "question_text",
        "current_goal",
    )
    intent: dict[str, Any] = {}
    for key in keys:
        value = context.get(key)
        if value not in (None, "", [], {}):
            intent[key] = value
    parameters = context.get("parameters")
    if isinstance(parameters, dict):
        for key in ("question_text", "current_intent_context", "user_intent", "task_request"):
            value = parameters.get(key)
            if value not in (None, "", [], {}):
                intent[f"parameters.{key}"] = value
    return intent


def extract_procedural_memory_constraints(context: dict[str, Any]) -> list[str]:
    constraints = _coerce_text_list(
        context.get("procedural_memory_constraints") or context.get("g38_procedural_constraints"),
        limit=20,
    )
    memory_service = context.get("memory_service")
    list_procedural_records = getattr(memory_service, "list_procedural_records", None)
    if callable(list_procedural_records):
        try:
            for record in list_procedural_records()[:40]:
                tags = [str(item).lower() for item in (getattr(record, "tags", []) or [])]
                text = str(
                    getattr(record, "summary", "")
                    or getattr(record, "content", "")
                    or getattr(record, "title", "")
                    or ""
                ).strip()
                payload = getattr(record, "payload", {}) or {}
                payload_text = " ".join(str(value) for value in payload.values() if value not in (None, "", [], {}))
                combined = f"{text} {payload_text}".lower()
                if any(token in combined for token in ("constraint", "redline", "red line", "禁止", "红线", "不可绕过")) or "procedural" in tags:
                    constraints.append(text or payload_text)
                if len(constraints) >= 20:
                    break
        except Exception:
            logger.exception("Q7 procedural memory constraint extraction failed")
    return list(dict.fromkeys(item for item in constraints if str(item).strip()))[:20]
