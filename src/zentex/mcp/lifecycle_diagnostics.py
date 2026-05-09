from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from zentex.mcp.models import McpServerConfig, McpServerRuntimeState


SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26"}


@dataclass(frozen=True)
class McpManagementDiagnosticReport:
    generated_at: str
    checks: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    metrics: dict[str, Any]
    completion: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "checks": self.checks,
            "issues": self.issues,
            "metrics": self.metrics,
            "completion": self.completion,
        }


@dataclass(frozen=True)
class McpFaultInjectionReport:
    generated_at: str
    passed: bool
    cases: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"generated_at": self.generated_at, "passed": self.passed, "cases": self.cases}


def build_mcp_management_diagnostic_report(
    *,
    configs: list[McpServerConfig],
    states: list[McpServerRuntimeState],
    schema_cache: dict[str, dict[str, Any]],
    schema_drift_events: list[dict[str, Any]],
    audit_entries: list[Any],
) -> McpManagementDiagnosticReport:
    payloads = [_entry_payload(entry) for entry in audit_entries]
    mcp_payloads = [payload for payload in payloads if payload.get("server_id")]
    invocation_payloads = [payload for payload in mcp_payloads if payload.get("phase") in {"completed", "failed"}]
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    registration_issues = _registration_issues(configs)
    issues.extend(registration_issues)
    checks.append(_check("server_registration_validation", not registration_issues and bool(configs), f"{len(configs)} server profile(s) registered"))

    protocol_issues = [
        _issue("protocol_version_incompatible", config.server_id, "critical", f"unsupported protocol_version={config.protocol_version}")
        for config in configs
        if config.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS
    ]
    issues.extend(protocol_issues)
    checks.append(_check("protocol_version_compatibility", not protocol_issues and bool(configs), "registered servers use supported MCP protocol versions"))

    degraded_states = [state for state in states if state.status != "online"]
    issues.extend(
        _issue("transport_degraded", state.server_id, "major", state.error_message or "server is not online")
        for state in degraded_states
    )
    checks.append(_check("transport_health_detection", not degraded_states and bool(states), f"{len(states) - len(degraded_states)}/{len(states)} server(s) online"))

    drift_issues = [
        _issue("schema_drift", str(event.get("server_id")), "major", f"tool schema drift: {event.get('tool_name')}")
        for event in schema_drift_events
    ]
    issues.extend(drift_issues)
    checks.append(_check("tool_schema_consistency", not drift_issues and bool(schema_cache), f"{len(schema_cache)} cached tool schema group(s) tracked"))

    boundary_issues = _permission_boundary_issues(states, configs)
    issues.extend(boundary_issues)
    checks.append(_check("permission_boundary_detection", not boundary_issues and bool(states), "MCP tool scopes match declared permission boundaries"))

    duplicate_tool_issues = _duplicate_tool_issues(states)
    issues.extend(duplicate_tool_issues)
    checks.append(_check("duplicate_tool_conflict_detection", bool(duplicate_tool_issues) or len(states) <= 1, f"{len(duplicate_tool_issues)} duplicate tool conflict(s) found"))

    audit_issues = _audit_issues(invocation_payloads)
    issues.extend(audit_issues)
    checks.append(_check("audit_chain_completeness", bool(invocation_payloads) and not audit_issues, f"{len(invocation_payloads)} invocation audit event(s) checked"))

    error_codes = {payload.get("error_code") for payload in invocation_payloads}
    issues.extend(
        _issue("classified_mcp_error", str(payload.get("server_id") or "unknown"), "major", f"error_code={payload.get('error_code')}")
        for payload in invocation_payloads
        if payload.get("status") == "failed" and payload.get("error_code")
    )
    checks.append(
        _check(
            "tool_call_failure_classification",
            bool(error_codes & {"mcp_bad_json", "mcp_empty_response", "mcp_permission_denied", "mcp_transport_error"}),
            f"classified error codes={sorted(str(code) for code in error_codes if code)}",
        )
    )

    metrics = {
        "server_count": len(configs),
        "online_server_count": sum(1 for state in states if state.status == "online"),
        "tool_count": sum(state.tool_count for state in states),
        "schema_cache_count": sum(len(tools) for tools in schema_cache.values()),
        "schema_drift_count": len(schema_drift_events),
        "invocation_audit_count": len(invocation_payloads),
        "classified_failure_count": sum(1 for payload in invocation_payloads if payload.get("status") == "failed"),
        "registration_rejection_count": sum(1 for payload in mcp_payloads if payload.get("status") == "rejected"),
    }
    completion = build_mcp_completion_assessment(checks=checks, metrics=metrics, invocation_payloads=invocation_payloads)
    return McpManagementDiagnosticReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        issues=issues,
        metrics=metrics,
        completion=completion,
    )


def build_mcp_fault_injection_report(report: McpManagementDiagnosticReport) -> McpFaultInjectionReport:
    checks = {check["name"]: check for check in report.checks}
    issue_codes = {issue["code"] for issue in report.issues}
    metrics = report.metrics
    cases = [
        {
            "name": "bad_json_classified",
            "passed": "mcp_bad_json" in _classified_codes(report),
            "evidence": "bad JSON response produced mcp_bad_json",
        },
        {
            "name": "empty_response_classified",
            "passed": "mcp_empty_response" in _classified_codes(report),
            "evidence": "empty response produced mcp_empty_response",
        },
        {
            "name": "version_incompatibility_detector_ran",
            "passed": "protocol_version_compatibility" in checks,
            "evidence": checks.get("protocol_version_compatibility", {}).get("detail"),
        },
        {
            "name": "schema_drift_detector_ran",
            "passed": "schema_drift" in issue_codes or metrics.get("schema_cache_count", 0) > 0,
            "evidence": f"{metrics.get('schema_drift_count', 0)} drift event(s)",
        },
        {
            "name": "permission_denial_classified",
            "passed": "mcp_permission_denied" in _classified_codes(report),
            "evidence": "permission denial produced mcp_permission_denied",
        },
        {
            "name": "server_disconnect_detector_ran",
            "passed": "transport_health_detection" in checks,
            "evidence": checks.get("transport_health_detection", {}).get("detail"),
        },
        {
            "name": "duplicate_tool_conflict_detector_ran",
            "passed": "duplicate_tool_conflict_detection" in checks,
            "evidence": checks.get("duplicate_tool_conflict_detection", {}).get("detail"),
        },
        {
            "name": "audit_chain_verified",
            "passed": bool(checks.get("audit_chain_completeness", {}).get("passed")),
            "evidence": checks.get("audit_chain_completeness", {}).get("detail"),
        },
    ]
    return McpFaultInjectionReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        passed=all(case["passed"] for case in cases),
        cases=cases,
    )


def build_mcp_completion_assessment(
    *,
    checks: list[dict[str, Any]],
    metrics: dict[str, Any],
    invocation_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    checks_by_name = {check["name"]: check for check in checks}
    error_codes = {payload.get("error_code") for payload in invocation_payloads}
    return {
        "registration_complete": bool(checks_by_name.get("server_registration_validation", {}).get("passed"))
        and metrics.get("schema_cache_count", 0) > 0,
        "handshake_complete": bool(checks_by_name.get("protocol_version_compatibility", {}).get("passed"))
        and bool(checks_by_name.get("transport_health_detection", {}).get("passed")),
        "tool_governance_complete": bool(checks_by_name.get("tool_schema_consistency", {}).get("passed"))
        and "duplicate_tool_conflict_detection" in checks_by_name
        and "permission_boundary_detection" in checks_by_name,
        "real_completion": metrics.get("invocation_audit_count", 0) >= 4
        and {"mcp_bad_json", "mcp_empty_response", "mcp_permission_denied"}.issubset(error_codes)
        and bool(checks_by_name.get("audit_chain_completeness", {}).get("passed")),
    }


def build_mcp_unavailable_diagnostic_report(error_message: str) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": [{"name": "mcp_service_assembly", "passed": False, "detail": error_message}],
        "issues": [{"code": "mcp_service_unavailable", "server_id": "mcp-assembly", "severity": "critical", "detail": error_message}],
        "metrics": {"server_count": 0, "online_server_count": 0},
        "completion": {
            "registration_complete": False,
            "handshake_complete": False,
            "tool_governance_complete": False,
            "real_completion": False,
        },
    }


def build_mcp_unavailable_fault_report(error_message: str) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "cases": [{"name": "mcp_service_assembly", "passed": False, "evidence": error_message}],
    }


def _registration_issues(configs: list[McpServerConfig]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for config in configs:
        if config.server_id in seen:
            issues.append(_issue("duplicate_server_id", config.server_id, "critical", "server_id is duplicated"))
        seen.add(config.server_id)
        if config.transport_type in {"http", "sse"} and not config.command.startswith(("http://", "https://")):
            issues.append(_issue("endpoint_invalid", config.server_id, "critical", "http/sse transport requires an HTTP endpoint"))
        if config.auth_mode not in {"none", "bearer", "api_key", "oauth_pkce"}:
            issues.append(_issue("auth_mode_invalid", config.server_id, "critical", "auth_mode is not supported"))
    return issues


def _permission_boundary_issues(
    states: list[McpServerRuntimeState],
    configs: list[McpServerConfig],
) -> list[dict[str, Any]]:
    by_id = {config.server_id: config for config in configs}
    issues: list[dict[str, Any]] = []
    for state in states:
        config = by_id.get(state.server_id)
        if config is None:
            continue
        allowed = set(config.scope)
        for tool in state.tools:
            if tool.mutates_state and "write" not in allowed:
                issues.append(_issue("permission_boundary_violation", state.server_id, "critical", f"tool {tool.tool_name} mutates state outside write scope"))
    return issues


def _duplicate_tool_issues(states: list[McpServerRuntimeState]) -> list[dict[str, Any]]:
    owners: dict[str, list[str]] = {}
    for state in states:
        for tool in state.tools:
            owners.setdefault(tool.tool_name, []).append(state.server_id)
    return [
        _issue("duplicate_tool_definition", ",".join(sorted(server_ids)), "major", f"tool {tool_name} is exposed by multiple servers")
        for tool_name, server_ids in owners.items()
        if len(set(server_ids)) > 1
    ]


def _audit_issues(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = {"server_id", "tool_name", "trace_id", "phase", "status", "request", "response", "error_code"}
    issues: list[dict[str, Any]] = []
    for payload in payloads:
        missing = sorted(key for key in required if key not in payload)
        if missing:
            issues.append(_issue("audit_chain_missing", str(payload.get("server_id") or "unknown"), "critical", f"audit payload missing fields: {missing}"))
    return issues


def _classified_codes(report: McpManagementDiagnosticReport) -> set[str]:
    return {
        str(issue["detail"]).rsplit("=", 1)[-1]
        for issue in report.issues
        if issue["code"] == "classified_mcp_error"
    }


def _entry_payload(entry: Any) -> dict[str, Any]:
    if isinstance(entry, dict):
        payload = entry.get("payload") or {}
    else:
        payload = getattr(entry, "payload", {}) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def _issue(code: str, server_id: str, severity: str, detail: str) -> dict[str, Any]:
    return {"code": code, "server_id": server_id, "severity": severity, "detail": detail}
