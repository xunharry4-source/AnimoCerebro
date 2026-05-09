from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.nine_questions.q5_what_am_i_allowed_to_do.service import (
    load_public_output as load_q5_public_output,
)

from zentex.common.scoped_llm_prompt import build_scoped_llm_request

_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_PROMPT_METADATA_KEYS = (
    "question_id",
    "question_text",
    "trace_id",
    "turn_id",
    "request_id",
    "question_driver_refs",
)


def build_q6_internal_llm_request(*, context: dict[str, Any]) -> dict[str, Any]:
    prompt_context = {
        key: context[key]
        for key in _PROMPT_METADATA_KEYS
        if context.get(key) not in (None, "", [], {})
    }
    prompt_context.update(
        {
            "Q5_AllowedInternalObjectives": _extract_q5_allowed_internal_objectives(context),
            "LivingSelfModel_Snapshot": _extract_living_self_model_snapshot(context),
        }
    )
    return build_scoped_llm_request(
        question_id="q6",
        scope="internal",
        template_dir=_TEMPLATE_DIR,
        context=prompt_context,
        title="Q6 Internal Plan Constraints",
        intent="Assess costs, risks, safeguards, pause conditions, stop conditions, and rollback requirements for Q5-approved internal objectives.",
        purpose="Constrain downstream internal planning without re-deciding Q5 allowance or writing Q8/Q9 implementation steps.",
        error_prefix="q6_internal",
    )


def _extract_q5_allowed_internal_objectives(context: dict[str, Any]) -> Any:
    objective_slice = context.get("q6_q5_internal_objective_slice")
    if objective_slice not in (None, "", [], {}):
        return _project_q5_allowed_objectives_for_q6(objective_slice)
    q5_public_output = load_q5_public_output(
        db_path=context.get("nine_question_state_db_path"),
        session_id=str(context.get("session_id") or "nq-baseline"),
    )
    q5_output = q5_public_output["q5_internal_authorization_boundary"]
    allowed = q5_output.get("allowed_internal_objectives_with_conditions")
    if allowed not in (None, "", [], {}):
        return _project_q5_allowed_objectives_for_q6(allowed)
    return None


def _extract_living_self_model_snapshot(context: dict[str, Any]) -> Any:
    return (
        context.get("LivingSelfModel_Snapshot")
        or context.get("LivingSelfModel_Current_State")
        or context.get("living_self_model_snapshot")
        or context.get("living_self_model_current_state")
        or {}
    )


def _project_q5_allowed_objectives_for_q6(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    projected: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        objective: dict[str, Any] = {}
        for key in (
            "objective_number",
            "candidate_description",
            "objective",
            "compliance_condition",
            "objective_type",
            "signal_or_gap_addressed",
            "objective_rationale",
            "capability_evidence_refs",
        ):
            value = item.get(key)
            if value not in (None, "", [], {}):
                objective[key] = value
        rules = _project_controlled_rules_for_q6(item.get("controlled_rules"))
        if rules:
            objective["controlled_rules"] = rules
        if objective:
            projected.append(objective)
    return projected


def _project_controlled_rules_for_q6(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    projected: dict[str, Any] = {}
    for key in (
        "source_compliance_condition",
        "allowed_scope",
        "mandatory_guardrails",
        "non_bypassable_constraints",
        "risk_refs",
    ):
        cleaned = _dedupe_non_empty(value.get(key))
        if cleaned not in (None, "", [], {}):
            projected[key] = cleaned
    rule_refs = value.get("rule_refs")
    if isinstance(rule_refs, list) and rule_refs:
        projected["rule_ref_count"] = len([item for item in rule_refs if str(item).strip()])
    return projected


def _dedupe_non_empty(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    cleaned: list[Any] = []
    seen: set[str] = set()
    for item in value:
        fingerprint = str(item).strip()
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        cleaned.append(item)
    return cleaned
