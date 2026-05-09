from __future__ import annotations

from typing import Any

from fastapi import Request

from zentex.module_logs import build_module_log_content, record_module_log


build_management_log_content = build_module_log_content


def record_module_management_log(
    request: Request,
    *,
    source_module: str,
    module_label: str,
    action: str,
    action_label: str,
    object_id: str,
    object_label: str | None = None,
    before_status: str | None = None,
    after_status: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    operator_id: str | None = None,
    status: str | None = None,
) -> None:
    module_log_service = getattr(request.app.state, "module_log_service", None)
    record_module_log(
        module_log_service,
        source_module=source_module,
        module_label=module_label,
        action=action,
        action_label=action_label,
        object_id=object_id,
        object_label=object_label,
        before_status=before_status,
        after_status=after_status,
        reason=reason,
        details=details,
        operator_id=operator_id or "web-console",
        status=status,
    )
