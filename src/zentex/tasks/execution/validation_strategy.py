from __future__ import annotations

from typing import Any, Dict


async def apply_validation_strategy(
    *,
    contract: Dict[str, Any],
    rule_verdict: Dict[str, Any],
    context: Dict[str, Any],
    runtime: Dict[str, Any],
) -> Dict[str, Any]:
    strategy = str(contract.get("verification_strategy") or "rule").strip().lower()
    if strategy == "rule":
        return {
            "strategy": "rule",
            "rule_verdict": rule_verdict,
            "llm_verdict": None,
            "passed": bool(rule_verdict.get("passed")),
            "failure_code": "" if rule_verdict.get("passed") else str(rule_verdict.get("failure_code") or "RULE_VALIDATION_FAILED"),
        }

    llm_gateway = runtime.get("llm_validation_gateway")
    if llm_gateway is None or not callable(getattr(llm_gateway, "validate", None)):
        return {
            "strategy": strategy,
            "rule_verdict": rule_verdict,
            "llm_verdict": None,
            "passed": False,
            "failure_code": "LLM_VALIDATION_REQUIRED_BUT_NOT_EXECUTED",
            "message": "Contract requires LLM validation but no LLM validation gateway was provided",
        }
    if strategy == "hybrid" and rule_verdict.get("passed") is not True:
        return {
            "strategy": "hybrid",
            "rule_verdict": rule_verdict,
            "llm_verdict": None,
            "passed": False,
            "failure_code": str(rule_verdict.get("failure_code") or "RULE_GATE_FAILED"),
            "message": "Hybrid validation stopped before LLM because rule/readback gate failed",
        }
    llm_verdict = await llm_gateway.validate(context=context, contract=contract, rule_verdict=rule_verdict)
    passed = bool(getattr(llm_verdict, "passed", False) if not isinstance(llm_verdict, dict) else llm_verdict.get("passed"))
    return {
        "strategy": strategy,
        "rule_verdict": rule_verdict,
        "llm_verdict": llm_verdict if isinstance(llm_verdict, dict) else getattr(llm_verdict, "__dict__", {}),
        "passed": passed,
        "failure_code": "" if passed else "LLM_VALIDATION_FAILED",
    }
