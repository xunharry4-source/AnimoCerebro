from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from zentex.environment import scouter as scouter_module
from zentex.environment.models import (
    HealthStatus,
    MemoryPressureLevel,
    NetworkHealthStatus,
    PhysicalHostState,
)


class HostSamplingAuditIssue(BaseModel):
    """One host-sampling default/fallback issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class HostSamplingAuditError(RuntimeError):
    """Raised when host sampling can mask unavailable metrics as zero."""

    def __init__(self, message: str, *, issues: list[HostSamplingAuditIssue]) -> None:
        self.issues = issues
        detail = "; ".join(f"{issue.path}: {issue.reason}" for issue in issues)
        super().__init__(f"{message}: {detail}" if detail else message)


class HostSamplingFieldAudit(BaseModel):
    """Audit result for one PhysicalHostState field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field_name: str = Field(min_length=1)
    expected_unavailable_value: Any
    actual_model_default: Any
    status: Literal["passed"]


class HostSamplingKeywordAudit(BaseModel):
    """Audit result for one sample_host_state constructor keyword."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    constructor_keyword: str = Field(min_length=1)
    source_expression: str = Field(min_length=1)
    status: Literal["passed"]


class HostSamplingAuditReport(BaseModel):
    """Report proving host sampling does not use fake zero defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_status: Literal["passed"]
    checked_model_fields: list[HostSamplingFieldAudit] = Field(default_factory=list)
    checked_constructor_keywords: list[HostSamplingKeywordAudit] = Field(default_factory=list)
    checked_failure_functions: list[str] = Field(default_factory=list)


_OPTIONAL_METRIC_FIELDS: tuple[str, ...] = (
    "memory_used_ratio",
    "memory_total_bytes",
    "memory_available_bytes",
    "cpu_load_percent",
    "cpu_count",
    "disk_usage_percent",
    "disk_free_bytes",
)

_UNKNOWN_ENUM_FIELDS: dict[str, Any] = {
    "memory_pressure": MemoryPressureLevel.UNKNOWN,
    "network_health": NetworkHealthStatus.UNKNOWN,
    "overall_health": HealthStatus.UNKNOWN,
}

_CONSTRUCTOR_KEYWORDS: dict[str, str] = {
    "memory_used_ratio": "memory_ratio",
    "memory_total_bytes": "memory_total",
    "memory_available_bytes": "memory_available",
    "cpu_load_percent": "cpu_load",
    "cpu_count": "cpu_count",
    "disk_usage_percent": "disk_usage",
    "disk_free_bytes": "disk_free",
}

_FAILURE_FUNCTIONS: tuple[str, ...] = (
    "_read_linux_memory_info",
    "_read_darwin_memory_info",
    "_read_memory_info",
    "_read_cpu_load",
    "_get_cpu_count",
    "_read_disk_usage",
)


def audit_host_sampling_defaults() -> HostSamplingAuditReport:
    """Audit that host metric failures are represented as None/UNKNOWN, not zero."""

    issues: list[HostSamplingAuditIssue] = []
    field_audits = _audit_model_defaults(issues)
    keyword_audits = _audit_sample_constructor(issues)
    checked_failure_functions = _audit_failure_returns(issues)

    if issues:
        raise HostSamplingAuditError("host sampling default audit failed", issues=issues)

    return HostSamplingAuditReport(
        audit_status="passed",
        checked_model_fields=field_audits,
        checked_constructor_keywords=keyword_audits,
        checked_failure_functions=checked_failure_functions,
    )


def _audit_model_defaults(issues: list[HostSamplingAuditIssue]) -> list[HostSamplingFieldAudit]:
    results: list[HostSamplingFieldAudit] = []
    fields = PhysicalHostState.model_fields

    for field_name in _OPTIONAL_METRIC_FIELDS:
        actual_default = fields[field_name].default
        if actual_default is not None:
            issues.append(
                HostSamplingAuditIssue(
                    path=f"PhysicalHostState.{field_name}",
                    reason=f"expected unavailable metric default None, found {actual_default!r}",
                )
            )
            continue
        results.append(
            HostSamplingFieldAudit(
                field_name=field_name,
                expected_unavailable_value=None,
                actual_model_default=actual_default,
                status="passed",
            )
        )

    for field_name, expected_default in _UNKNOWN_ENUM_FIELDS.items():
        actual_default = fields[field_name].default
        if actual_default != expected_default:
            issues.append(
                HostSamplingAuditIssue(
                    path=f"PhysicalHostState.{field_name}",
                    reason=f"expected unavailable status {expected_default!r}, found {actual_default!r}",
                )
            )
            continue
        results.append(
            HostSamplingFieldAudit(
                field_name=field_name,
                expected_unavailable_value=expected_default,
                actual_model_default=actual_default,
                status="passed",
            )
        )
    return results


def _audit_sample_constructor(
    issues: list[HostSamplingAuditIssue],
) -> list[HostSamplingKeywordAudit]:
    function_node = _function_node(scouter_module.EnvironmentScouter.sample_host_state)
    constructor_call = _find_physical_host_state_call(function_node)
    if constructor_call is None:
        issues.append(
            HostSamplingAuditIssue(
                path="EnvironmentScouter.sample_host_state",
                reason="PhysicalHostState constructor call not found",
            )
        )
        return []

    keyword_map = {keyword.arg: keyword.value for keyword in constructor_call.keywords}
    results: list[HostSamplingKeywordAudit] = []
    for keyword_name, expected_name in _CONSTRUCTOR_KEYWORDS.items():
        value_node = keyword_map.get(keyword_name)
        if value_node is None:
            issues.append(
                HostSamplingAuditIssue(
                    path=f"PhysicalHostState({keyword_name}=...)",
                    reason="constructor keyword missing",
                )
            )
            continue
        if not isinstance(value_node, ast.Name) or value_node.id != expected_name:
            issues.append(
                HostSamplingAuditIssue(
                    path=f"PhysicalHostState({keyword_name}=...)",
                    reason=f"expected direct variable {expected_name}, found {ast.unparse(value_node)}",
                )
            )
            continue
        results.append(
            HostSamplingKeywordAudit(
                constructor_keyword=keyword_name,
                source_expression=ast.unparse(value_node),
                status="passed",
            )
        )
    return results


def _audit_failure_returns(issues: list[HostSamplingAuditIssue]) -> list[str]:
    module_tree = ast.parse(inspect.getsource(scouter_module))
    checked: list[str] = []
    for node in ast.walk(module_tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in _FAILURE_FUNCTIONS:
            continue
        checked.append(node.name)
        for handler in [item for item in ast.walk(node) if isinstance(item, ast.ExceptHandler)]:
            for return_node in [item for item in ast.walk(handler) if isinstance(item, ast.Return)]:
                if _return_contains_numeric_zero(return_node.value):
                    issues.append(
                        HostSamplingAuditIssue(
                            path=f"{node.name}:line{getattr(return_node, 'lineno', '?')}",
                            reason="exception path returns numeric zero instead of None/UNKNOWN",
                        )
                    )
    missing = sorted(set(_FAILURE_FUNCTIONS) - set(checked))
    for function_name in missing:
        issues.append(
            HostSamplingAuditIssue(
                path=function_name,
                reason="expected sampling function not found",
            )
        )
    return checked


def _function_node(function: Any) -> ast.FunctionDef:
    source = textwrap.dedent(inspect.getsource(function))
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node
    raise HostSamplingAuditError(
        "host sampling default audit failed",
        issues=[
            HostSamplingAuditIssue(
                path=getattr(function, "__name__", "<unknown>"),
                reason="function AST not found",
            )
        ],
    )


def _find_physical_host_state_call(function_node: ast.FunctionDef) -> ast.Call | None:
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "PhysicalHostState":
            return node
    return None


def _return_contains_numeric_zero(node: ast.AST | None) -> bool:
    if node is None:
        return False
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and child.value == 0:
            return True
    return False
