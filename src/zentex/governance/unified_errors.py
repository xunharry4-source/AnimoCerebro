from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


ErrorModule = Literal["plugin", "task", "agent", "cli", "mcp", "safety", "web", "memory", "unknown"]
ErrorCategory = Literal[
    "input",
    "auth",
    "timeout",
    "protocol",
    "dependency",
    "state",
    "safety",
    "audit",
    "rollback",
    "unknown",
]
ErrorStage = Literal[
    "perception",
    "nine_questions",
    "dispatch",
    "plugin_call",
    "agent_negotiation",
    "cli_execution",
    "mcp_call",
    "safety_review",
    "execution_receipt",
    "memory_writeback",
    "web_api",
]
ErrorSeverity = Literal["info", "warning", "error", "critical"]
ErrorAudience = Literal["internal", "api", "web", "audit"]
DispositionAction = Literal["retry", "degrade", "block", "escalate", "rollback", "manual_review"]


class ErrorContextRefs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = None
    task_id: str | None = None
    decision_id: str | None = None
    receipt_id: str | None = None
    plugin_id: str | None = None
    agent_id: str | None = None
    server_id: str | None = None
    replay_id: str | None = None


class RawErrorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: ErrorModule
    raw_error_type: str = Field(min_length=1)
    raw_message: str = Field(min_length=1)
    stage: ErrorStage | None = None
    trace_id: str = Field(min_length=1)
    related_refs: ErrorContextRefs = Field(default_factory=ErrorContextRefs)
    evidence_refs: list[str] = Field(default_factory=list)
    source_status_code: int | None = Field(default=None, ge=100, le=599)


class UnifiedError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_id: str
    error_code: str
    error_category: ErrorCategory
    error_stage: ErrorStage
    severity: ErrorSeverity
    retryable: bool
    user_visible_message: str
    operator_message: str
    recovery_hint: str
    trace_id: str
    related_refs: dict[str, str] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    source_module: ErrorModule
    raw_error_type: str
    occurred_at: str


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: dict[str, Any]
    trace_id: str
    related_refs: dict[str, str] = Field(default_factory=dict)


class UnifiedErrorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unified_error: UnifiedError
    api_envelope: ErrorEnvelope
    web_envelope: ErrorEnvelope
    audit_payload: dict[str, Any]
    disposition: dict[str, Any]


MAPPING_RULES: dict[tuple[ErrorModule, str], dict[str, Any]] = {
    ("plugin", "load_failed"): {
        "code": "PLUGIN_LOAD_FAILED",
        "category": "dependency",
        "stage": "plugin_call",
        "severity": "error",
        "retryable": True,
        "recovery": "retry_after_plugin_registry_refresh",
    },
    ("plugin", "schema_error"): {
        "code": "PLUGIN_SCHEMA_INVALID",
        "category": "protocol",
        "stage": "plugin_call",
        "severity": "error",
        "retryable": False,
        "recovery": "reject_plugin_and_request_schema_fix",
    },
    ("plugin", "version_conflict"): {
        "code": "PLUGIN_VERSION_CONFLICT",
        "category": "state",
        "stage": "plugin_call",
        "severity": "error",
        "retryable": False,
        "recovery": "pin_compatible_plugin_version_or_rollback",
    },
    ("plugin", "fake_health"): {
        "code": "PLUGIN_FAKE_HEALTH",
        "category": "audit",
        "stage": "plugin_call",
        "severity": "critical",
        "retryable": False,
        "recovery": "quarantine_plugin_and_escalate",
    },
    ("task", "invalid_state_transition"): {
        "code": "TASK_STATE_TRANSITION_INVALID",
        "category": "state",
        "stage": "dispatch",
        "severity": "error",
        "retryable": False,
        "recovery": "reload_task_state_and_require_manual_review",
    },
    ("task", "dependency_cycle"): {
        "code": "TASK_DEPENDENCY_CYCLE",
        "category": "state",
        "stage": "dispatch",
        "severity": "critical",
        "retryable": False,
        "recovery": "block_dispatch_until_dependency_graph_is_repaired",
    },
    ("agent", "handshake_failed"): {
        "code": "AGENT_HANDSHAKE_FAILED",
        "category": "dependency",
        "stage": "agent_negotiation",
        "severity": "error",
        "retryable": True,
        "recovery": "retry_handshake_then_route_to_alternate_agent",
    },
    ("agent", "fake_capability"): {
        "code": "AGENT_FAKE_CAPABILITY",
        "category": "audit",
        "stage": "agent_negotiation",
        "severity": "critical",
        "retryable": False,
        "recovery": "disable_agent_and_escalate_to_operator",
    },
    ("cli", "command_not_found"): {
        "code": "CLI_COMMAND_NOT_FOUND",
        "category": "dependency",
        "stage": "cli_execution",
        "severity": "error",
        "retryable": False,
        "recovery": "check_runtime_path_or_use_registered_alternative",
    },
    ("cli", "timeout"): {
        "code": "CLI_TIMEOUT",
        "category": "timeout",
        "stage": "cli_execution",
        "severity": "warning",
        "retryable": True,
        "recovery": "retry_with_timeout_budget_or_degraded_path",
    },
    ("cli", "injection_pattern"): {
        "code": "CLI_INJECTION_PATTERN",
        "category": "safety",
        "stage": "cli_execution",
        "severity": "critical",
        "retryable": False,
        "recovery": "block_command_and_require_security_review",
    },
    ("mcp", "handshake_failed"): {
        "code": "MCP_HANDSHAKE_FAILED",
        "category": "dependency",
        "stage": "mcp_call",
        "severity": "error",
        "retryable": True,
        "recovery": "retry_handshake_or_disable_server",
    },
    ("mcp", "bad_json"): {
        "code": "MCP_BAD_JSON",
        "category": "protocol",
        "stage": "mcp_call",
        "severity": "error",
        "retryable": False,
        "recovery": "reject_response_and_request_protocol_fix",
    },
    ("mcp", "disconnect"): {
        "code": "MCP_DISCONNECTED",
        "category": "dependency",
        "stage": "mcp_call",
        "severity": "warning",
        "retryable": True,
        "recovery": "retry_or_failover_to_alternate_mcp_server",
    },
    ("safety", "redline_hit"): {
        "code": "SAFETY_REDLINE_HIT",
        "category": "safety",
        "stage": "safety_review",
        "severity": "critical",
        "retryable": False,
        "recovery": "block_execution_and_escalate",
    },
    ("safety", "permission_denied"): {
        "code": "SAFETY_PERMISSION_DENIED",
        "category": "auth",
        "stage": "safety_review",
        "severity": "critical",
        "retryable": False,
        "recovery": "request_permission_or_abort",
    },
    ("safety", "audit_chain_missing"): {
        "code": "SAFETY_AUDIT_CHAIN_MISSING",
        "category": "audit",
        "stage": "safety_review",
        "severity": "critical",
        "retryable": False,
        "recovery": "block_until_audit_chain_is_restored",
    },
}


def unified_error_catalog() -> dict[str, Any]:
    return {
        "required_fields": [
            "error_code",
            "error_category",
            "error_stage",
            "severity",
            "retryable",
            "user_visible_message",
            "operator_message",
            "recovery_hint",
            "trace_id",
            "related_refs",
        ],
        "categories": [
            "input",
            "auth",
            "timeout",
            "protocol",
            "dependency",
            "state",
            "safety",
            "audit",
            "rollback",
            "unknown",
        ],
        "modules": ["plugin", "task", "agent", "cli", "mcp", "safety", "web", "memory", "unknown"],
        "mapped_error_codes": sorted(rule["code"] for rule in MAPPING_RULES.values()),
        "audiences": ["internal", "api", "web", "audit"],
        "disposition_actions": ["retry", "degrade", "block", "escalate", "rollback", "manual_review"],
    }


def map_raw_error(raw: RawErrorInput) -> UnifiedErrorReport:
    rule = _resolve_rule(raw)
    error = UnifiedError(
        error_id=f"unified-error:{uuid4().hex}",
        error_code=rule["code"],
        error_category=rule["category"],
        error_stage=raw.stage or rule["stage"],
        severity=rule["severity"],
        retryable=bool(rule["retryable"]),
        user_visible_message=_user_message(raw.module, rule),
        operator_message=_operator_message(raw, rule),
        recovery_hint=rule["recovery"],
        trace_id=raw.trace_id,
        related_refs=_related_refs(raw.related_refs),
        evidence_refs=list(raw.evidence_refs),
        source_module=raw.module,
        raw_error_type=raw.raw_error_type,
        occurred_at=datetime.now(timezone.utc).isoformat(),
    )
    disposition = _disposition(error)
    return UnifiedErrorReport(
        unified_error=error,
        api_envelope=_envelope(error, "api"),
        web_envelope=_envelope(error, "web"),
        audit_payload=_audit_payload(error, raw, disposition),
        disposition=disposition,
    )


def unified_error_statistics(reports: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: Counter[str] = Counter()
    by_stage: Counter[str] = Counter()
    by_module: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    retryable_count = 0
    critical_count = 0
    for report in reports:
        error = report["unified_error"]
        by_category[error["error_category"]] += 1
        by_stage[error["error_stage"]] += 1
        by_module[error["source_module"]] += 1
        by_action[report["disposition"]["action"]] += 1
        retryable_count += 1 if error["retryable"] else 0
        critical_count += 1 if error["severity"] == "critical" else 0
    return {
        "total_error_count": len(reports),
        "retryable_count": retryable_count,
        "critical_count": critical_count,
        "by_category": dict(sorted(by_category.items())),
        "by_stage": dict(sorted(by_stage.items())),
        "by_module": dict(sorted(by_module.items())),
        "by_action": dict(sorted(by_action.items())),
    }


def _resolve_rule(raw: RawErrorInput) -> dict[str, Any]:
    key = (raw.module, raw.raw_error_type.strip().lower())
    if key in MAPPING_RULES:
        return MAPPING_RULES[key]
    lowered = f"{raw.raw_error_type} {raw.raw_message}".lower()
    if "timeout" in lowered:
        return {
            "code": f"{raw.module.upper()}_TIMEOUT",
            "category": "timeout",
            "stage": raw.stage or "web_api",
            "severity": "warning",
            "retryable": True,
            "recovery": "retry_with_budget_or_degraded_path",
        }
    if "permission" in lowered or "denied" in lowered or "auth" in lowered:
        return {
            "code": f"{raw.module.upper()}_PERMISSION_DENIED",
            "category": "auth",
            "stage": raw.stage or "safety_review",
            "severity": "critical",
            "retryable": False,
            "recovery": "request_permission_or_abort",
        }
    if "json" in lowered or "schema" in lowered or "protocol" in lowered:
        return {
            "code": f"{raw.module.upper()}_PROTOCOL_ERROR",
            "category": "protocol",
            "stage": raw.stage or "web_api",
            "severity": "error",
            "retryable": False,
            "recovery": "reject_payload_and_fix_protocol_mapping",
        }
    return {
        "code": f"{raw.module.upper()}_UNKNOWN",
        "category": "unknown",
        "stage": raw.stage or "web_api",
        "severity": "error",
        "retryable": False,
        "recovery": "escalate_to_operator_with_trace_context",
    }


def _related_refs(refs: ErrorContextRefs) -> dict[str, str]:
    return {key: str(value) for key, value in refs.model_dump().items() if value}


def _user_message(module: ErrorModule, rule: dict[str, Any]) -> str:
    category = str(rule["category"])
    if category == "timeout":
        return f"{module} operation timed out. The system kept the trace for recovery."
    if category in {"auth", "safety"}:
        return f"{module} operation was blocked by safety or permission controls."
    if category == "protocol":
        return f"{module} returned data that failed the required protocol contract."
    if category == "state":
        return f"{module} operation cannot continue because the state is inconsistent."
    if category == "audit":
        return f"{module} operation was blocked because audit evidence is incomplete."
    return f"{module} operation failed and was converted into a unified error."


def _operator_message(raw: RawErrorInput, rule: dict[str, Any]) -> str:
    return (
        f"{raw.module}:{raw.raw_error_type} mapped to {rule['code']} "
        f"at trace {raw.trace_id}: {raw.raw_message}"
    )


def _envelope(error: UnifiedError, audience: ErrorAudience) -> ErrorEnvelope:
    base = {
        "error_id": error.error_id,
        "error_code": error.error_code,
        "error_category": error.error_category,
        "error_stage": error.error_stage,
        "severity": error.severity,
        "retryable": error.retryable,
        "message": error.user_visible_message,
        "recovery_hint": error.recovery_hint,
    }
    if audience == "web":
        base["display_message"] = error.user_visible_message
    return ErrorEnvelope(error=base, trace_id=error.trace_id, related_refs=error.related_refs)


def _audit_payload(error: UnifiedError, raw: RawErrorInput, disposition: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "unified_error_mapped",
        "error_id": error.error_id,
        "error_code": error.error_code,
        "error_category": error.error_category,
        "error_stage": error.error_stage,
        "severity": error.severity,
        "retryable": error.retryable,
        "operator_message": error.operator_message,
        "recovery_hint": error.recovery_hint,
        "trace_id": error.trace_id,
        "related_refs": error.related_refs,
        "evidence_refs": error.evidence_refs,
        "raw_error_type": raw.raw_error_type,
        "source_status_code": raw.source_status_code,
        "disposition": disposition,
    }


def _disposition(error: UnifiedError) -> dict[str, Any]:
    action: DispositionAction
    if error.severity == "critical":
        if error.error_category == "rollback":
            action = "rollback"
        else:
            action = "escalate"
    elif error.error_category in {"safety", "audit", "state", "auth"}:
        action = "block"
    elif error.retryable:
        action = "retry"
    elif error.error_category in {"timeout", "dependency"}:
        action = "degrade"
    else:
        action = "manual_review"
    return {
        "action": action,
        "retry_allowed": error.retryable and action == "retry",
        "requires_human": action in {"escalate", "manual_review", "rollback"},
        "recovery_hint": error.recovery_hint,
    }
