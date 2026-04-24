from __future__ import annotations

"""
Helper utilities for nine questions router.

Contains general-purpose helper functions used across all question modules.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

# Note: startup_snapshot import removed - module not available in web_console context
# This is handled in plugins/nine_questions instead


def _normalize_health_status(value: object) -> str:
    """Normalize health status values to standard categories."""
    normalized = str(value or "").strip().lower()
    if normalized in {"healthy", "ok", "online", "low", "normal"}:
        return "healthy"
    if normalized in {"degraded", "degrade", "medium", "warn", "warning"}:
        return "degrade"
    if normalized:
        return normalized
    return "unknown"


def _serialize_contract_payload(value: object) -> dict[str, Optional[object]]:
    """Serialize contract payload to JSON-compatible dict."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return None


def _coerce_string_list(value: object) -> list[str]:
    """Coerce value to list of strings, filtering empty strings."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _humanize_constraint_text(value: object) -> Optional[str]:
    """Humanize constraint text with predefined labels."""
    labels = {
        "NO_FAKE_RUNTIME_STATE": "禁止伪造运行态事实或虚构系统状态",
        "NO_SKIP_AUDIT": "禁止跳过审计记录、证据链和可追溯性要求",
        "NO_UNAUTHORIZED_WRITE_ACTION": "禁止未授权写入、修改或执行会产生副作用的动作",
    }
    text = str(value or "").strip()
    if not text:
        return None
    return labels.get(text, text)


def _merge_context_payloads(*payloads: object) -> dict[str, Any]:
    """Merge multiple context payloads, preferring non-empty values."""
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


def _normalize_ratio(value: object) -> float:
    """Normalize ratio value to 0.0-1.0 range."""
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1.0:
            numeric = numeric / 100.0
        return max(0.0, min(1.0, numeric))
    return 0.0


def _build_runtime_workspace_snapshot(
    *,
    workspace_root: str,
    cognitive_registry: Any,
    execution_registry: Optional[object],
    task_service: Optional[object],
    host_telemetry_plugin: Optional[object] = None,
) -> dict[str, object]:
    raise RuntimeError(
        "_build_runtime_workspace_snapshot is not implemented in web_console; "
        "runtime workspace snapshots must come from the real kernel/runtime pipeline."
    )
