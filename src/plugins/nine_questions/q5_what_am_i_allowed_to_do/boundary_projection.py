from __future__ import annotations

from typing import Any


def normalize_q5_internal_boundary(llm_output: dict[str, Any]) -> dict[str, Any]:
    if llm_output.get("type") != "InternalGoalComplianceAssessment":
        raise RuntimeError("q5_internal_boundary_missing")
    payload = llm_output
    allowed = _objective_condition_list(
        payload.get("allowed_internal_objectives_with_conditions"),
        error_prefix="q5_internal",
    )
    blocked = _blocked_objective_list(
        payload.get("blocked_internal_objectives"),
        error_prefix="q5_internal",
    )
    system_safety_boundary = str(payload.get("system_safety_boundary") or "").strip()
    if not system_safety_boundary:
        raise RuntimeError("q5_internal_system_safety_boundary_missing")
    for item in allowed:
        condition = item["compliance_condition"].strip()
        if _is_empty_condition(condition):
            raise RuntimeError("q5_internal_allowed_objective_missing_compliance_condition")
    boundary = {
        "scope": "internal",
        "boundary_type": "InternalGoalComplianceAssessment",
        "type": "InternalGoalComplianceAssessment",
        "system_safety_boundary": system_safety_boundary,
        "blocked_internal_objectives": blocked,
        "non_bypassable_internal_constraints": _string_list(payload.get("non_bypassable_internal_constraints")),
        "identity_kernel_protection_hits": _string_list(payload.get("identity_kernel_protection_hits")),
        "safety_module_protection_hits": _string_list(payload.get("safety_module_protection_hits")),
        "supervision_module_protection_hits": _string_list(payload.get("supervision_module_protection_hits")),
        "memory_integrity_risks": _string_list(payload.get("memory_integrity_risks")),
        "continuity_risks": _string_list(payload.get("continuity_risks")),
        "allowed_internal_objectives_with_conditions": allowed,
    }
    if not any(
        boundary[key]
        for key in (
            "blocked_internal_objectives",
            "non_bypassable_internal_constraints",
            "identity_kernel_protection_hits",
            "safety_module_protection_hits",
            "supervision_module_protection_hits",
            "memory_integrity_risks",
            "continuity_risks",
            "allowed_internal_objectives_with_conditions",
        )
    ):
        raise RuntimeError("q5_internal_boundary_not_meaningful")
    return boundary


def normalize_q5_external_boundary(llm_output: dict[str, Any]) -> dict[str, Any]:
    if llm_output.get("type") != "ExternalGoalComplianceAssessment":
        raise RuntimeError("q5_external_boundary_missing")
    payload = llm_output
    allowed = _objective_condition_list(
        payload.get("allowed_external_objectives_with_conditions"),
        error_prefix="q5_external",
    )
    blocked = _blocked_objective_list(
        payload.get("blocked_external_objectives"),
        error_prefix="q5_external",
    )
    system_safety_boundary = str(payload.get("system_safety_boundary") or "").strip()
    if not system_safety_boundary:
        raise RuntimeError("q5_external_system_safety_boundary_missing")
    for item in allowed:
        condition = item["compliance_condition"].strip()
        if _is_empty_condition(condition):
            raise RuntimeError("q5_external_allowed_objective_missing_compliance_condition")
    boundary = {
        "scope": "external",
        "boundary_type": "ExternalGoalComplianceAssessment",
        "type": "ExternalGoalComplianceAssessment",
        "system_safety_boundary": system_safety_boundary,
        "blocked_external_objectives": blocked,
        "requires_cloud_audit": _string_list(payload.get("requires_cloud_audit")),
        "requires_human_confirmation": _string_list(payload.get("requires_human_confirmation")),
        "permission_boundary_hits": _string_list(payload.get("permission_boundary_hits")),
        "data_exfiltration_risks": _string_list(payload.get("data_exfiltration_risks")),
        "unauthorized_mutation_risks": _string_list(payload.get("unauthorized_mutation_risks")),
        "allowed_external_objectives_with_conditions": allowed,
    }
    if not any(
        boundary[key]
        for key in (
            "blocked_external_objectives",
            "requires_cloud_audit",
            "requires_human_confirmation",
            "permission_boundary_hits",
            "data_exfiltration_risks",
            "unauthorized_mutation_risks",
            "allowed_external_objectives_with_conditions",
        )
    ):
        raise RuntimeError("q5_external_boundary_not_meaningful")
    return boundary


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]
    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = str(raw or "").strip()
        if text and text not in seen:
            items.append(text)
            seen.add(text)
    return items


def _blocked_objective_list(value: Any, *, error_prefix: str) -> list[dict[str, str]]:
    if value in (None, "", [], {}):
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{error_prefix}_blocked_objectives_invalid")
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise RuntimeError(f"{error_prefix}_blocked_objective_invalid")
        objective_number = str(raw.get("objective_number") or "").strip()
        objective = str(raw.get("objective") or "").strip()
        violation_reason = str(raw.get("violation_reason") or "").strip()
        if not objective or not violation_reason:
            raise RuntimeError(f"{error_prefix}_blocked_objective_incomplete")
        key = (objective_number, objective, violation_reason)
        if key not in seen:
            items.append({
                "objective_number": objective_number,
                "objective": objective,
                "violation_reason": violation_reason
            })
            seen.add(key)
    return items


def _objective_condition_list(value: Any, *, error_prefix: str) -> list[dict[str, str]]:
    if value in (None, "", [], {}):
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{error_prefix}_allowed_objectives_invalid")
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise RuntimeError(f"{error_prefix}_allowed_objective_invalid")
        objective_number = str(raw.get("objective_number") or "").strip()
        objective = str(raw.get("objective") or "").strip()
        compliance_condition = str(raw.get("compliance_condition") or "").strip()
        if not objective or not compliance_condition:
            raise RuntimeError(f"{error_prefix}_allowed_objective_incomplete")
        key = (objective_number, objective, compliance_condition)
        if key not in seen:
            items.append({
                "objective_number": objective_number,
                "objective": objective,
                "compliance_condition": compliance_condition
            })
            seen.add(key)
    return items


def _is_empty_condition(value: str) -> bool:
    lowered = value.strip().lower()
    empty_values = {
        "无",
        "无需",
        "无条件",
        "不需要限制",
        "none",
        "no",
        "n/a",
        "not required",
        "unconditional",
    }
    return lowered in empty_values or len(value.strip()) < 6
