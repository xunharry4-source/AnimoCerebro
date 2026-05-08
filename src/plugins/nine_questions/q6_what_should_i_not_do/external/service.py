from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q6_what_should_i_not_do.external.llm_prompt import (
    build_q6_external_llm_request,
)
from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
    safe_provider_plugin_id,
)

logger = logging.getLogger(__name__)

_Q6_EXTERNAL_ROOT_KEY = "ExternalPlanConstraintSet"
_COST_TEXT_FIELDS = (
    "physical_side_effects",
    "blast_radius",
    "data_exposure_risk",
    "file_or_remote_mutation_risk",
    "monetary_cost",
    "compute_cost",
    "latency_cost",
    "rollback_difficulty",
)
_SAFEGUARD_FIELDS = (
    "read_only_probe_first",
    "sandbox_first",
    "dry_run_first",
    "backup_required",
    "confirmation_required",
)
_VERIFICATION_TEXT_FIELDS = ("evidence_requirements", "receipt_requirements")
_HALT_TEXT_FIELDS = ("pause_conditions", "stop_conditions")
_EMPTY_TEXT_VALUES = {"无", "不需要", "无需", "暂无", "n/a", "none", "not required"}
_HIGH_RISK_KEYWORDS = ("高", "极难", "不可逆", "删除", "覆盖", "破坏", "destructive", "irreversible", "delete", "overwrite")


def run_q6_external_llm_and_save(context: dict[str, Any]) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    turn_id = str(context.get("turn_id") or context.get("request_id") or "unknown-turn")
    trace_id = f"{context.get('trace_id') or 'q6'}:external"
    request_id = f"q6-external-request:{uuid4().hex}"
    decision_id = f"q6-external:{uuid4().hex}"
    started = perf_counter()
    provider = require_model_provider(context)
    transcript_store = require_transcript_store(context)
    request = build_q6_external_llm_request(context=dict(context))
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="nine_question_q6_external_consequence",
        question_ref="q6:external",
        question_driver_refs=context.get("question_driver_refs"),
        decision_id=decision_id,
        trace_id=trace_id,
    )
    llm_input = {
        "request_id": request_id,
        "decision_id": decision_id,
        "provider_plugin_id": safe_provider_plugin_id(provider),
        "system_prompt": request["system_prompt"],
        "prompt": request["prompt"],
        "context": request["model_context"],
        "caller_context": caller_context.model_dump(mode="json"),
    }
    logger.info("[Q6 EXTERNAL LLM INPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_input))
    record_model_invoked(
        transcript_store,
        session_id=session_id,
        turn_id=turn_id,
        trace_id=trace_id,
        source=__name__,
        payload={"q6_external_llm_input": llm_input},
    )
    persist_question_module_output(
        context,
        question_id="q6",
        module_id="q6_external_llm_request",
        payload={"q6_external_llm_input": llm_input},
        status="prepared",
        output_kind="llm_request",
        rollback_available=False,
        retry_available=True,
        trace_id=trace_id,
    )
    try:
        from plugins.nine_questions.q6_what_should_i_not_do.external.instructor_contract import (
            generate_external_plan_constraint_set_with_instructor_contract,
        )

        llm_output = generate_external_plan_constraint_set_with_instructor_contract(
            provider,
            prompt=f"{request['system_prompt']}\n\n{request['prompt']}",
            context=request["model_context"],
            caller_context=caller_context,
            metadata={
                "question_id": "q6",
                "scope": "external",
                "max_json_repair_attempts": 0,
                "output_truncation_forbidden": True,
            },
        )
        external_result = llm_output
        logger.info("[Q6 EXTERNAL LLM OUTPUT] trace_id=%s payload=%s", trace_id, json_safe_payload(llm_output))
        persist_question_module_output(
            context,
            question_id="q6",
            module_id="q6_external_consequence_llm",
            payload={
                "q6_external_llm_output": llm_output,
                "q6_external_consequence_profile": external_result,
            },
            status="completed",
            output_kind="inference",
            trace_id=trace_id,
        )
        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q6_external_llm_output": llm_output,
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        )
        return {
            "llm_input": llm_input,
            "llm_output": llm_output,
            "result": external_result,
        }
    except Exception as exc:
        record_model_failed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source=__name__,
            payload={
                "q6_external_llm_input": llm_input,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
            },
        )
        logger.exception("[Q6 EXTERNAL LLM ERROR] trace_id=%s", trace_id)
        raise


def _extract_external_result(llm_output: dict[str, Any]) -> dict[str, Any]:
    if llm_output.get("type") != _Q6_EXTERNAL_ROOT_KEY:
        raise RuntimeError(f"q6_external_result_missing_root:{_Q6_EXTERNAL_ROOT_KEY}")

    constraints = llm_output.get("objective_constraints")
    if not isinstance(constraints, list):
        raise RuntimeError("q6_external_result_invalid:objective_constraints")
    if not constraints:
        raise RuntimeError("q6_external_result_empty:objective_constraints")

    normalized_constraints = [_normalize_objective_constraint(item) for item in constraints]
    return {
        "type": _Q6_EXTERNAL_ROOT_KEY,
        "objective_constraints": normalized_constraints,
    }


def _normalize_objective_constraint(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("q6_external_result_invalid:objective_constraint")
    cost = _normalize_text_mapping(value.get("consequence_and_cost"), _COST_TEXT_FIELDS, "consequence_and_cost")
    safeguards = _normalize_safeguards(value.get("execution_safeguards"), cost)
    verification = _normalize_text_mapping(
        value.get("verification_contracts"),
        _VERIFICATION_TEXT_FIELDS,
        "verification_contracts",
    )
    halt = _normalize_text_mapping(value.get("halt_conditions"), _HALT_TEXT_FIELDS, "halt_conditions")
    for key in _HALT_TEXT_FIELDS:
        _reject_empty_text(halt[key], f"halt_conditions.{key}")
    return {
        "objective_ref": _require_non_empty_text(value, "objective_ref"),
        "consequence_and_cost": cost,
        "execution_safeguards": safeguards,
        "verification_contracts": verification,
        "halt_conditions": halt,
        "rationality_assessment": _require_non_empty_text(value, "rationality_assessment"),
    }


def _normalize_text_mapping(value: Any, fields: tuple[str, ...], parent: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RuntimeError(f"q6_external_result_invalid:{parent}")
    return {
        key: _require_non_empty_text(value, key, field_path=f"{parent}.{key}")
        for key in fields
    }


def _normalize_safeguards(value: Any, cost: dict[str, str]) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise RuntimeError("q6_external_result_invalid:execution_safeguards")
    safeguards: dict[str, bool] = {}
    for key in _SAFEGUARD_FIELDS:
        raw = value.get(key)
        if not isinstance(raw, bool):
            raise RuntimeError(f"q6_external_result_invalid:execution_safeguards.{key}")
        safeguards[key] = raw
    risk_text = f"{cost['file_or_remote_mutation_risk']} {cost['rollback_difficulty']}".lower()
    is_high_risk = any(keyword in risk_text for keyword in _HIGH_RISK_KEYWORDS)
    has_protection = (
        safeguards["backup_required"]
        or safeguards["dry_run_first"]
        or safeguards["sandbox_first"]
    )
    if is_high_risk and not has_protection:
        raise RuntimeError("q6_external_result_safeguard_mismatch:high_mutation_or_rollback_risk")
    return safeguards


def _require_non_empty_text(payload: dict[str, Any], key: str, *, field_path: str | None = None) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"q6_external_result_invalid:{field_path or key}")
    text = value.strip()
    _reject_empty_text(text, field_path or key)
    _reject_plan_step_text(text, field_path or key)
    return text


def _reject_empty_text(value: str, key: str) -> None:
    normalized = value.strip().lower()
    if len(value.strip()) < 5 or normalized in _EMPTY_TEXT_VALUES:
        raise RuntimeError(f"q6_external_result_empty:{key}")


def _reject_plan_step_text(value: str, key: str) -> None:
    lowered = value.lower()
    forbidden_terms = (
        "task_id",
        "subtask_id",
        "resource_lock",
        "资源锁",
        "步骤1",
        "步骤 1",
        "第一步执行",
        "执行步骤",
        "实现计划",
        "建单",
    )
    if any(term in lowered for term in forbidden_terms):
        raise RuntimeError(f"q6_external_result_contains_plan_step:{key}")
