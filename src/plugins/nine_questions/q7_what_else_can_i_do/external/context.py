from __future__ import annotations

from typing import Any


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


def extract_safety_rejection_history(context: dict[str, Any], upstream_context: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    for key in (
        "rejected_operation_records",
        "safety_rejection_history",
        "safety_gate_rejections",
        "safety_gate_audit_log",
        "cloud_audit_rejections",
        "cloud_audit_decisions",
        "g12_safety_gate_history",
        "g30_cloud_audit_history",
    ):
        candidates.extend(_coerce_text_list(context.get(key), limit=30))
        candidates.extend(_coerce_text_list(upstream_context.get(key), limit=30))
    return list(dict.fromkeys(item for item in candidates if item))[:30]
