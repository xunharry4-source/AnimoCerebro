from __future__ import annotations

from typing import Any, Dict, List


def verify_capability(
    *,
    context: Dict[str, Any],
    observations: List[Dict[str, Any]],
    result_validation: Dict[str, Any],
    contract: Dict[str, Any],
) -> Dict[str, Any]:
    failures: List[Dict[str, Any]] = []
    if result_validation.get("passed") is not True:
        failures.append({"verifier_id": "result_validation_gate", "reason": "result validation did not pass"})
    if not observations:
        failures.append({"verifier_id": "observation_required", "reason": "no observations found"})

    latest_payload = observations[-1].get("payload") if observations and isinstance(observations[-1], dict) else {}
    for rule in contract.get("verification_rules") or []:
        if not isinstance(rule, dict):
            continue
        rule_type = str(rule.get("type") or "").strip()
        field = str(rule.get("field") or rule.get("path") or "").strip()
        value = _json_path(latest_payload, field) if field else None
        if rule_type == "required_field" and value in (None, "", [], {}):
            failures.append({"verifier_id": f"required_field:{field}", "reason": "required field missing"})
        if rule_type == "enum_value" and value not in set(rule.get("allowed_values") or []):
            failures.append({"verifier_id": f"enum_value:{field}", "reason": f"value {value!r} not allowed"})

    passed = not failures
    return {
        "overall_passed": passed,
        "passed": passed,
        "strategy": "capability_contract",
        "confidence_score": 1.0 if passed else 0.0,
        "summary": "Capability verification passed" if passed else "Capability verification failed",
        "failure_code": "" if passed else "CAPABILITY_VERIFICATION_FAILED",
        "verifier_results": [
            {
                "verifier_id": item["verifier_id"],
                "verifier_type": "rule_based",
                "status": "failed",
                "passed": False,
                "summary": item["reason"],
            }
            for item in failures
        ],
        "check_results": {"failure_count": len(failures), "executor_type": context.get("executor_type")},
    }


def _json_path(payload: Any, path: str) -> Any:
    if not path:
        return payload
    normalized = path[2:] if path.startswith("$.") else path
    value = payload
    for part in normalized.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value
