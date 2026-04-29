from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from zentex.cli.models import CliToolRegistrationConfig, CliToolRuntimeState


_DANGEROUS_ENV_KEYS = {"PATH", "PYTHONPATH", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "SHELL", "HOME"}
_MUTATING_EXECUTABLES = {
    "rm",
    "del",
    "delete",
    "format",
    "mkfs",
    "dd",
    "chmod",
    "chown",
    "write",
    "overwrite",
    "truncate",
    "kill",
    "stop",
    "reboot",
    "shutdown",
    "sudo",
    "su",
    "apt",
    "brew",
    "npm",
    "pip",
    "git",
    "cp",
    "mv",
}
_MUTATING_ARG_FRAGMENTS = {
    "write_text",
    "write_bytes",
    ".write(",
    "open(",
    "truncate(",
    "unlink(",
    "remove(",
    "rmtree",
    "mkdir(",
    "rename(",
    "replace(",
    "chmod(",
    "chown(",
    "git commit",
    "git push",
    "git reset",
    "git checkout",
    "rm ",
    "rm -",
    "touch ",
    "mkdir ",
    "mv ",
    "cp ",
    "tee ",
    ">",
}


@dataclass(frozen=True)
class CliClosureDiagnosticReport:
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
class CliFaultInjectionReport:
    generated_at: str
    passed: bool
    cases: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"generated_at": self.generated_at, "passed": self.passed, "cases": self.cases}


def build_cli_execution_diagnostic_report(
    *,
    configs: list[CliToolRegistrationConfig],
    states: list[CliToolRuntimeState],
    audit_entries: list[Any],
) -> CliClosureDiagnosticReport:
    payloads = [_entry_payload(entry) for entry in audit_entries]
    cli_payloads = [payload for payload in payloads if payload.get("tool_name")]
    registration_rejections = [payload for payload in cli_payloads if payload.get("status") == "rejected"]
    invocation_payloads = [payload for payload in cli_payloads if "exit_code" in payload]
    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    command_missing = _command_missing_issues(configs)
    issues.extend(command_missing)
    checks.append(
        _check(
            "command_existence_detection",
            not command_missing,
            f"{len(configs) - len(command_missing)}/{len(configs)} registered commands are reachable",
        )
    )

    version_issues = _version_probe_issues(configs)
    issues.extend(version_issues)
    checks.append(
        _check(
            "version_probe_detection",
            not version_issues,
            f"{len(configs) - len(version_issues)}/{len(configs)} registered commands passed --version probe",
        )
    )

    schema_issues = _schema_issues(configs)
    issues.extend(schema_issues)
    checks.append(_check("parameter_schema_validation", not schema_issues, "registered configs satisfy CLI schema constraints"))

    readonly_issues = _readonly_truth_issues(configs)
    issues.extend(readonly_issues)
    checks.append(_check("read_only_authenticity_detection", not readonly_issues, "read-only registrations do not contain static mutating signatures"))

    env_issues = _environment_pollution_issues(configs)
    issues.extend(env_issues)
    checks.append(_check("environment_pollution_detection", not env_issues, "registered env overlays avoid host-polluting keys"))

    dangerous_blocks = [payload for payload in invocation_payloads if payload.get("failure_category") == "dangerous_argument"]
    checks.append(
        _check(
            "dangerous_argument_blocking",
            bool(dangerous_blocks),
            f"{len(dangerous_blocks)} dangerous invocation(s) were blocked before transport execution",
        )
    )

    audit_issues = _audit_completeness_issues(invocation_payloads)
    issues.extend(audit_issues)
    checks.append(
        _check(
            "audit_field_completeness",
            bool(invocation_payloads) and not audit_issues,
            f"{len(invocation_payloads)} invocation audit event(s) include trace/result/summary fields",
        )
    )

    runtime_issues = _runtime_signal_issues(invocation_payloads)
    issues.extend(runtime_issues)
    checks.append(
        _check(
            "runtime_failure_classification",
            any(payload.get("failure_category") in {"non_zero_exit", "timeout", "dangerous_argument"} for payload in invocation_payloads),
            "non-zero, timeout, or preflight failures are classified in audit",
        )
    )

    checks.append(
        _check(
            "registration_rejection_audit",
            bool(registration_rejections) or not configs,
            f"{len(registration_rejections)} registration rejection audit event(s) recorded",
        )
    )

    metrics = {
        "tool_count": len(configs),
        "active_tool_count": sum(1 for state in states if state.status == "active"),
        "audit_event_count": len(cli_payloads),
        "invocation_audit_count": len(invocation_payloads),
        "registration_rejection_count": len(registration_rejections),
        "successful_invocations": sum(1 for payload in invocation_payloads if payload.get("status") == "success"),
        "failed_invocations": sum(1 for payload in invocation_payloads if payload.get("status") in {"failed", "timeout", "transport_error"}),
        "preflight_blocked_invocations": len(dangerous_blocks),
    }
    completion = build_cli_completion_assessment(checks=checks, configs=configs, invocation_payloads=invocation_payloads)
    return CliClosureDiagnosticReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        issues=issues,
        metrics=metrics,
        completion=completion,
    )


def build_cli_fault_injection_report(report: CliClosureDiagnosticReport) -> CliFaultInjectionReport:
    checks_by_name = {check["name"]: check for check in report.checks}
    issues_by_code = {issue["code"] for issue in report.issues}
    metrics = report.metrics
    cases = [
        {
            "name": "command_missing_detector_ran",
            "passed": "command_existence_detection" in checks_by_name,
            "evidence": checks_by_name.get("command_existence_detection", {}).get("detail"),
        },
        {
            "name": "non_zero_exit_classified",
            "passed": "non_zero_exit" in issues_by_code,
            "evidence": "non-zero CLI execution produced a classified audit issue",
        },
        {
            "name": "read_only_or_shell_injection_blocked",
            "passed": metrics.get("preflight_blocked_invocations", 0) > 0,
            "evidence": f"{metrics.get('preflight_blocked_invocations', 0)} preflight block(s)",
        },
        {
            "name": "timeout_killed_and_audited",
            "passed": "timeout" in issues_by_code,
            "evidence": "timeout execution returned timeout status and audit fields",
        },
        {
            "name": "stderr_pollution_detected",
            "passed": "stderr_pollution" in issues_by_code,
            "evidence": "successful command with stderr output was flagged",
        },
        {
            "name": "environment_pollution_detector_ran",
            "passed": "environment_pollution_detection" in checks_by_name,
            "evidence": checks_by_name.get("environment_pollution_detection", {}).get("detail"),
        },
        {
            "name": "audit_completeness_verified",
            "passed": bool(checks_by_name.get("audit_field_completeness", {}).get("passed")),
            "evidence": checks_by_name.get("audit_field_completeness", {}).get("detail"),
        },
    ]
    return CliFaultInjectionReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        passed=all(case["passed"] for case in cases),
        cases=cases,
    )


def build_cli_completion_assessment(
    *,
    checks: list[dict[str, Any]],
    configs: list[CliToolRegistrationConfig],
    invocation_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    checks_by_name = {check["name"]: check for check in checks}
    statuses = {payload.get("status") for payload in invocation_payloads}
    failure_categories = {payload.get("failure_category") for payload in invocation_payloads}
    return {
        "integration_complete": bool(configs)
        and bool(checks_by_name.get("command_existence_detection", {}).get("passed"))
        and bool(checks_by_name.get("parameter_schema_validation", {}).get("passed")),
        "audit_complete": bool(checks_by_name.get("audit_field_completeness", {}).get("passed")),
        "defense_complete": bool(checks_by_name.get("dangerous_argument_blocking", {}).get("passed"))
        and bool(checks_by_name.get("runtime_failure_classification", {}).get("passed")),
        "real_completion": bool(configs)
        and {"success", "failed", "timeout"}.issubset(statuses)
        and {"dangerous_argument", "non_zero_exit", "timeout"}.issubset(failure_categories)
        and bool(checks_by_name.get("audit_field_completeness", {}).get("passed")),
    }


def _command_missing_issues(configs: list[CliToolRegistrationConfig]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for config in configs:
        executable = config.command_executable
        exists = bool(shutil.which(executable)) if "/" not in executable else shutil.which(executable) is not None or _path_exists(executable)
        if not exists:
            issues.append(_issue("command_missing", config.tool_name, "critical", f"command is not reachable: {executable}"))
    return issues


def _version_probe_issues(configs: list[CliToolRegistrationConfig]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for config in configs:
        try:
            completed = subprocess.run(  # noqa: S603
                [config.command_executable, "--version"],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
        except Exception as exc:
            issues.append(_issue("version_probe_failed", config.tool_name, "major", f"--version probe failed: {exc}"))
            continue
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            issues.append(_issue("version_probe_failed", config.tool_name, "major", f"--version exit_code={completed.returncode}: {detail}"))
    return issues


def _schema_issues(configs: list[CliToolRegistrationConfig]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for config in configs:
        if any(not isinstance(arg, str) or arg == "" for arg in config.command_args):
            issues.append(_issue("argument_schema_invalid", config.tool_name, "critical", "command_args must contain non-empty strings"))
        if config.read_only_flag is False and not config.execution_domain.strip():
            issues.append(_issue("execution_domain_missing", config.tool_name, "critical", "mutating CLI tools must declare execution_domain"))
    return issues


def _readonly_truth_issues(configs: list[CliToolRegistrationConfig]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for config in configs:
        if not config.read_only_flag:
            continue
        executable = config.command_executable.strip().lower().rsplit("/", 1)[-1]
        rendered_args = " ".join(config.command_args).lower()
        if executable in _MUTATING_EXECUTABLES or any(fragment in rendered_args for fragment in _MUTATING_ARG_FRAGMENTS):
            issues.append(_issue("read_only_masquerade", config.tool_name, "critical", "read-only tool contains a static mutating signature"))
    return issues


def _environment_pollution_issues(configs: list[CliToolRegistrationConfig]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for config in configs:
        polluted = sorted(key for key in config.env if key in _DANGEROUS_ENV_KEYS or key.startswith("DYLD_"))
        if polluted:
            issues.append(_issue("environment_pollution", config.tool_name, "major", f"env overlay contains host-sensitive keys: {polluted}"))
    return issues


def _audit_completeness_issues(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = {"tool_name", "status", "trace_id", "exit_code", "stdout", "stderr", "command_line", "duration_ms"}
    issues: list[dict[str, Any]] = []
    for payload in payloads:
        missing = sorted(key for key in required if key not in payload)
        if missing:
            issues.append(_issue("audit_chain_missing", str(payload.get("tool_name") or "unknown"), "critical", f"audit payload missing fields: {missing}"))
    return issues


def _runtime_signal_issues(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for payload in payloads:
        tool_name = str(payload.get("tool_name") or "unknown")
        if payload.get("status") == "success" and str(payload.get("stderr") or "").strip():
            issues.append(_issue("stderr_pollution", tool_name, "minor", "command succeeded but emitted stderr output"))
        if payload.get("status") == "timeout":
            issues.append(_issue("timeout", tool_name, "major", "command timed out and was terminated by transport"))
        if payload.get("failure_category") == "non_zero_exit":
            issues.append(_issue("non_zero_exit", tool_name, "major", f"command exited with code {payload.get('exit_code')}"))
        if payload.get("failure_category") == "dangerous_argument":
            issues.append(_issue("dangerous_argument", tool_name, "critical", "dangerous CLI argument was blocked before execution"))
    return issues


def _entry_payload(entry: Any) -> dict[str, Any]:
    if isinstance(entry, dict):
        payload = entry.get("payload") or {}
    else:
        payload = getattr(entry, "payload", {}) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "detail": detail}


def _issue(code: str, tool_name: str, severity: str, detail: str) -> dict[str, Any]:
    return {"code": code, "tool_name": tool_name, "severity": severity, "detail": detail}


def _path_exists(path: str) -> bool:
    from pathlib import Path

    return Path(path).exists()
