from __future__ import annotations

from copy import deepcopy
from typing import Any


class Q7MeaningfulAssessmentError(RuntimeError):
    pass


class Q7CreativePossibilityError(RuntimeError):
    pass


INTERNAL_CREATIVE_CATEGORIES = {
    "alternative_internal_objectives",
    "new_reasoning_paths",
    "new_reflection_methods",
    "new_memory_architecture_options",
    "value_prompting_possibilities",
    "learning_opportunities",
    "self_evolution_possibilities",
    "pure_cognitive_plugin_ideas",
    "low_cost_internal_experiments",
}

POSSIBILITY_STATUSES = {
    "hypothetical",
    "needs_discovery",
    "needs_learning",
    "needs_verification",
    "needs_authorization",
    "ready_for_q4_objective_candidate",
}

EXTERNAL_CREATIVE_TYPES = {
    "public_competitor_signal_research",
    "content_quality_opportunities",
    "subreddit_rule_learning",
    "authorized_account_compliance_audit",
    "unregistered_agent_options",
    "unknown_cli_options",
    "new_mcp_server_options",
    "new_connector_options",
    "browser_or_saas_automation_options",
    "external_service_options",
    "collaboration_opportunities",
    "tool_learning_opportunities",
    "low_risk_probe_candidates",
}

EXTERNAL_POSSIBILITY_STATUSES = POSSIBILITY_STATUSES | {"needs_registration"}

EXTERNAL_ABUSE_PATTERNS = (
    "规避",
    "绕过",
    "指纹",
    "操纵",
    "批量",
    "水军",
    "封禁",
    "bypass",
    "fingerprint",
    "vote manipulation",
    "ban evasion",
    "sockpuppet",
)


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return str(value or "").strip()


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        items = [_text(item) for item in value]
    elif isinstance(value, tuple):
        items = [_text(item) for item in value]
    else:
        text = _text(value)
        items = [text] if text else []
    return list(dict.fromkeys(item for item in items if item))


def _first_dict(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _contains_macro_name(value: object) -> bool:
    if isinstance(value, str):
        return "{{" in value or "}}" in value
    if isinstance(value, dict):
        return any(_contains_macro_name(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_macro_name(item) for item in value)
    return False


def _contains_external_abuse_pattern(value: object) -> bool:
    text = _text(value).lower()
    return any(pattern in text for pattern in EXTERNAL_ABUSE_PATTERNS)


def _normalize_internal_creative_possibility(item: object, index: int) -> dict[str, str]:
    possibility = _as_dict(item)
    if not possibility:
        raise Q7CreativePossibilityError(f"q7_internal_creative_possibility_{index}_not_object")

    category = _text(possibility.get("category"))
    description = _text(possibility.get("description"))
    rationale = _text(possibility.get("rationale"))
    status = _text(possibility.get("possibility_status"))

    if category not in INTERNAL_CREATIVE_CATEGORIES:
        raise Q7CreativePossibilityError(f"q7_internal_creative_possibility_{index}_category_invalid")
    if status not in POSSIBILITY_STATUSES:
        raise Q7CreativePossibilityError(f"q7_internal_creative_possibility_{index}_status_invalid")
    if not description:
        raise Q7CreativePossibilityError(f"q7_internal_creative_possibility_{index}_description_missing")
    if not rationale:
        raise Q7CreativePossibilityError(f"q7_internal_creative_possibility_{index}_rationale_missing")
    if _contains_macro_name(possibility):
        raise Q7CreativePossibilityError(f"q7_internal_creative_possibility_{index}_macro_variable_leaked")

    return {
        "category": category,
        "description": description,
        "rationale": rationale,
        "possibility_status": status,
    }


def _normalize_external_creative_possibility(item: object, index: int) -> dict[str, str]:
    possibility = _as_dict(item)
    if not possibility:
        raise Q7CreativePossibilityError(f"q7_external_creative_possibility_{index}_not_object")

    possibility_type = _text(possibility.get("possibility_type"))
    description = _text(possibility.get("possibility_description"))
    status = _text(possibility.get("possibility_status"))
    rationale = _text(possibility.get("divergent_rationale"))

    if possibility_type not in EXTERNAL_CREATIVE_TYPES:
        raise Q7CreativePossibilityError(f"q7_external_creative_possibility_{index}_type_invalid")
    if status not in EXTERNAL_POSSIBILITY_STATUSES:
        raise Q7CreativePossibilityError(f"q7_external_creative_possibility_{index}_status_invalid")
    if not description:
        raise Q7CreativePossibilityError(f"q7_external_creative_possibility_{index}_description_missing")
    if not rationale:
        raise Q7CreativePossibilityError(f"q7_external_creative_possibility_{index}_rationale_missing")
    if _contains_macro_name(possibility):
        raise Q7CreativePossibilityError(f"q7_external_creative_possibility_{index}_macro_variable_leaked")
    if _contains_external_abuse_pattern(description) or _contains_external_abuse_pattern(rationale):
        raise Q7CreativePossibilityError(f"q7_external_creative_possibility_{index}_platform_abuse_pattern")

    return {
        "possibility_type": possibility_type,
        "possibility_description": description,
        "possibility_status": status,
        "divergent_rationale": rationale,
    }


def normalize_q7_internal_creative_possibility_set(llm_output: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(llm_output)
    body = _first_dict(payload, ("InternalCreativePossibilitySet", "Q7InternalCreativePossibilitySet")) or payload
    body = deepcopy(_as_dict(body))
    if body.get("type") != "InternalCreativePossibilitySet":
        raise Q7CreativePossibilityError("q7_internal_creative_possibility_set_type_invalid")
    raw_possibilities = body.get("creative_possibilities")
    if not isinstance(raw_possibilities, list):
        raise Q7CreativePossibilityError("q7_internal_creative_possibilities_not_list")
    normalized_possibilities = [
        _normalize_internal_creative_possibility(item, index)
        for index, item in enumerate(raw_possibilities)
    ]
    if not normalized_possibilities:
        raise Q7CreativePossibilityError("q7_internal_creative_possibilities_empty")

    categories = list(dict.fromkeys(item["category"] for item in normalized_possibilities))
    statuses = list(dict.fromkeys(item["possibility_status"] for item in normalized_possibilities))
    return {
        "type": "InternalCreativePossibilitySet",
        "scope": "internal",
        "creative_possibilities": normalized_possibilities,
        "creative_possibility_categories": categories,
        "possibility_statuses": statuses,
        "ready_for_q4_objective_candidates": [
            item
            for item in normalized_possibilities
            if item["possibility_status"] == "ready_for_q4_objective_candidate"
        ],
    }


def normalize_q7_external_creative_possibility_set(llm_output: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(llm_output)
    body = _first_dict(payload, ("ExternalCreativePossibilitySet", "Q7ExternalCreativePossibilitySet")) or payload
    body = deepcopy(_as_dict(body))
    if body.get("type") != "ExternalCreativePossibilitySet":
        raise Q7CreativePossibilityError("q7_external_creative_possibility_set_type_invalid")
    raw_possibilities = body.get("creative_possibilities")
    if not isinstance(raw_possibilities, list):
        raise Q7CreativePossibilityError("q7_external_creative_possibilities_not_list")
    normalized_possibilities = [
        _normalize_external_creative_possibility(item, index)
        for index, item in enumerate(raw_possibilities)
    ]
    if len(normalized_possibilities) < 3:
        raise Q7CreativePossibilityError("q7_external_creative_possibilities_minimum_3_required")

    possibility_types = list(dict.fromkeys(item["possibility_type"] for item in normalized_possibilities))
    if len(possibility_types) < 3:
        raise Q7CreativePossibilityError("q7_external_creative_possibilities_distinct_type_minimum_3_required")
    statuses = list(dict.fromkeys(item["possibility_status"] for item in normalized_possibilities))
    return {
        "type": "ExternalCreativePossibilitySet",
        "scope": "external",
        "creative_possibilities": normalized_possibilities,
        "creative_possibility_types": possibility_types,
        "possibility_statuses": statuses,
        "ready_for_q4_objective_candidates": [
            item
            for item in normalized_possibilities
            if item["possibility_status"] == "ready_for_q4_objective_candidate"
        ],
        "needs_registration_possibilities": [
            item for item in normalized_possibilities if item["possibility_status"] == "needs_registration"
        ],
    }


def _normalize_q7_assessment(
    *,
    scope: str,
    llm_output: dict[str, Any],
    wrapper_keys: tuple[str, ...],
    rejected_keys: tuple[str, ...],
) -> dict[str, Any]:
    body = _first_dict(llm_output, wrapper_keys) or llm_output
    body = deepcopy(_as_dict(body))

    hits = _string_list(body.get("current_red_line_hits") or body.get("current_redline_hits"))
    rejected: list[str] = []
    for key in rejected_keys:
        rejected.extend(_string_list(body.get(key)))
    constraints = _string_list(body.get("non_bypassable_constraints"))
    source_explanations = _string_list(
        body.get("ban_source_explanations")
        or body.get("constraint_sources_explanation")
        or body.get("source_explanations")
    )
    question_driver_refs = _string_list(body.get("question_driver_refs"))

    if not any((hits, rejected, constraints, source_explanations)):
        raise Q7MeaningfulAssessmentError(f"q7_{scope}_meaningful_assessment_missing")

    if not constraints:
        raise Q7MeaningfulAssessmentError(f"q7_{scope}_non_bypassable_constraints_missing")

    constraint_explanation = "; ".join(source_explanations)
    normalized = {
        "scope": scope,
        "current_red_line_hits": hits,
        "rejected_operation_records": list(dict.fromkeys(rejected)),
        "non_bypassable_constraints": constraints,
        "ban_source_explanations": source_explanations,
        "constraint_sources_explanation": constraint_explanation,
        "question_driver_refs": question_driver_refs,
    }
    if scope == "internal":
        normalized["rejected_cognitive_patterns"] = list(normalized["rejected_operation_records"])
    elif scope == "external":
        normalized["rejected_external_operations"] = list(normalized["rejected_operation_records"])
    return normalized


def normalize_q7_internal_assessment(llm_output: dict[str, Any]) -> dict[str, Any]:
    return normalize_q7_internal_creative_possibility_set(llm_output)


def normalize_q7_external_assessment(llm_output: dict[str, Any]) -> dict[str, Any]:
    return _normalize_q7_assessment(
        scope="external",
        llm_output=_as_dict(llm_output),
        wrapper_keys=(
            "Q7ExternalRedLineAssessment",
            "ExternalRedLineAssessment",
            "RedLineAssessment",
            "ExternalConstraintAssessment",
        ),
        rejected_keys=(
            "rejected_operation_records",
            "rejected_operations_log",
            "rejected_external_operations",
            "rejected_operations",
        ),
    )


def build_q7_internal_context_updates(internal: dict[str, Any]) -> dict[str, Any]:
    possibility_set = normalize_q7_internal_creative_possibility_set(internal)
    return {
        "q7_internal_creative_possibility_set": possibility_set,
        "q7_internal_creative_possibilities": possibility_set["creative_possibilities"],
        "q7_internal_possibility_statuses": possibility_set["possibility_statuses"],
        "q7_internal_ready_for_q4_objective_candidates": possibility_set["ready_for_q4_objective_candidates"],
    }


def build_q7_external_context_updates(external: dict[str, Any]) -> dict[str, Any]:
    possibility_set = normalize_q7_external_creative_possibility_set(external)
    return {
        "q7_external_creative_possibility_set": possibility_set,
        "q7_external_creative_possibilities": possibility_set["creative_possibilities"],
        "q7_external_possibility_statuses": possibility_set["possibility_statuses"],
        "q7_external_ready_for_q4_objective_candidates": possibility_set["ready_for_q4_objective_candidates"],
        "q7_external_needs_registration_possibilities": possibility_set["needs_registration_possibilities"],
    }
