from __future__ import annotations

from typing import Any, Dict, List


def validate_result(attempt: Dict[str, Any], observations: List[Dict[str, Any]], contract: Dict[str, Any]) -> Dict[str, Any]:
    result = attempt.get("result") if isinstance(attempt.get("result"), dict) else {}
    failures: List[Dict[str, Any]] = []
    if attempt.get("status") != "succeeded":
        failures.append({"field": "attempt.status", "reason": "attempt did not succeed"})

    output_schema = contract.get("output_schema") if isinstance(contract.get("output_schema"), dict) else {}
    required = output_schema.get("required") if isinstance(output_schema.get("required"), list) else []
    for field_name in required:
        if result.get(field_name) in (None, "", [], {}):
            failures.append({"field": str(field_name), "reason": "required output field missing"})

    for requirement in contract.get("evidence_requirements") or []:
        if not isinstance(requirement, dict):
            continue
        field_name = str(requirement.get("field") or "").strip()
        if not field_name:
            continue
        value = _json_path(result, field_name)
        if requirement.get("type") == "non_empty_list" and not value:
            failures.append({"field": field_name, "reason": "expected non-empty list evidence"})

    if not observations:
        failures.append({"field": "observations", "reason": "no observations available"})

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "validation_id": f"result-validation:{attempt.get('attempt_id')}",
        "field_results": failures,
        "semantic_results": [],
        "evidence_results": [],
        "failure_type": None if passed else "result_validation_failed",
        "failure_code": None if passed else "RESULT_VALIDATION_FAILED",
        "retryable": False,
    }


def _json_path(payload: Dict[str, Any], path: str) -> Any:
    value: Any = payload
    normalized = path[2:] if path.startswith("$.") else path
    for part in normalized.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value
