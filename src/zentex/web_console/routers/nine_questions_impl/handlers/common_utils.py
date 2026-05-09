from __future__ import annotations
"""Common utility functions for nine questions handlers.

Shared helpers used across multiple question handlers for data normalization,
payload serialization, and context merging.
"""

from typing import Any, Dict

from pydantic import BaseModel


def normalize_health_status(value: object) -> str:
    """Normalize health status strings to standard forms.
    
    Args:
        value: Health status to normalize
    
    Returns:
        Normalized status: "healthy", "degrade", or the original value
    """
    normalized = str(value or "").strip().lower()
    if normalized in {"healthy", "ok", "online", "low", "normal"}:
        return "healthy"
    if normalized in {"degraded", "degrade", "medium", "warn", "warning"}:
        return "degrade"
    if normalized:
        return normalized
    return "unknown"


def serialize_contract_payload(value: object) -> dict[str, Optional[object]]:
    """Serialize a contract payload to dictionary.
    
    Args:
        value: Pydantic model or dict to serialize
    
    Returns:
        Dictionary representation or None
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None


def coerce_string_list(value: object) -> list[str]:
    """Convert any value to a list of non-empty strings.
    
    Args:
        value: Value to coerce into string list
    
    Returns:
        List of non-empty strings
    """
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def normalize_ratio(value: object) -> float:
    """Normalize any value to a float between 0.0 and 1.0.
    
    Args:
        value: Value to normalize
    
    Returns:
        Float between 0.0 and 1.0
    """
    try:
        num = float(value)
        return max(0.0, min(1.0, num))
    except (ValueError, TypeError):
        return 0.0


def humanize_constraint_text(value: object) -> Optional[str]:
    """Humanize constraint code to readable Chinese text.
    
    Args:
        value: Constraint code or string
    
    Returns:
        Humanized constraint text or None
    """
    labels = {
        "NO_FAKE_RUNTIME_STATE": "禁止伪造运行态事实或虚构系统状态",
        "NO_SKIP_AUDIT": "禁止跳过审计记录、证据链和可追溯性要求",
        "NO_UNAUTHORIZED_WRITE_ACTION": "禁止未授权写入、修改或执行会产生副作用的动作",
    }
    text = str(value or "").strip()
    if not text:
        return None
    return labels.get(text, text)


def merge_context_payloads(*payloads: object) -> dict[str, Any]:
    """Merge multiple context payloads, preferring first non-empty values.
    
    Args:
        *payloads: Payloads to merge (dicts or other)
    
    Returns:
        Merged dictionary
    """
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if key not in merged:
                merged[key] = value
                continue
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                combined = dict(existing)
                for child_key, child_value in value.items():
                    if child_key not in combined or combined.get(child_key) in (None, "", [], {}):
                        combined[child_key] = child_value
                merged[key] = combined
            elif existing in (None, "", [], {}):
                merged[key] = value
    return merged
