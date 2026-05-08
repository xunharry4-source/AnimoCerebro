from __future__ import annotations

from copy import deepcopy
import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q5_what_am_i_allowed_to_do.external.service import (
    run_q5_external_llm_and_save,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do.internal.service import (
    run_q5_internal_llm_and_save,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q5
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class Q5WhatAmIAllowedToDoPlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q5
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q5"
    display_name: str = "Q5: 我被允许做什么"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_internal_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q5")
        internal_run = start_module_run(
            module_runs,
            "q5_internal_authorization_llm",
            source="plugins.nine_questions.q5.internal",
        )
        try:
            internal = run_q5_internal_llm_and_save(context)
            finish_module_run(internal_run)
        except Exception as exc:
            fail_module_run(internal_run, error_code="q5_internal_authorization_failed", error_message=str(exc))
            raise

        llm_output = {
            "q5_internal_llm_input": internal["llm_input"],
            "q5_internal_llm_output": internal["llm_output"],
        }
        public_boundary = _project_internal_public_boundary(
            internal["result"],
            internal_llm_input=internal["llm_input"],
        )
        context_updates = {
            "q5_internal_cannot_do_boundary": public_boundary,
            "q5_internal_authorization_boundary": deepcopy(public_boundary),
            "q5_internal_execution_diagnosis": {
                "authenticity_status": "completed",
                "diagnosis_code": "internal_llm_saved",
                "lane": "internal",
                "module_runs": list(module_runs),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        }
        return CognitiveToolResult(
            tool_id=f"{self.plugin_id}:internal",
            summary="Q5 internal cannot-do boundary saved as a normalized internal lane result.",
            llm_output=llm_output,
            context_updates=context_updates,
            proposals=[
                {"kind": "q5_internal_cannot_do_boundary", **public_boundary},
            ],
            confidence=0.75,
        )

    def run_external_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        module_runs = bind_module_runs(context, "q5")
        external_run = start_module_run(
            module_runs,
            "q5_external_authorization_llm",
            source="plugins.nine_questions.q5.external",
        )
        try:
            external = run_q5_external_llm_and_save(context)
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(external_run, error_code="q5_external_authorization_failed", error_message=str(exc))
            raise

        llm_output = {
            "q5_external_llm_input": external["llm_input"],
            "q5_external_llm_output": external["llm_output"],
        }
        public_boundary = _project_external_public_boundary(
            external["result"],
            external_llm_input=external["llm_input"],
        )
        context_updates = {
            "q5_external_cannot_do_boundary": public_boundary,
            "q5_external_authorization_boundary": deepcopy(public_boundary),
            "q5_external_execution_diagnosis": {
                "authenticity_status": "completed",
                "diagnosis_code": "external_llm_saved",
                "lane": "external",
                "module_runs": list(module_runs),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        }
        return CognitiveToolResult(
            tool_id=f"{self.plugin_id}:external",
            summary="Q5 external cannot-do boundary saved as a normalized external lane result.",
            llm_output=llm_output,
            context_updates=context_updates,
            proposals=[
                {"kind": "q5_external_cannot_do_boundary", **public_boundary},
            ],
            confidence=0.75,
        )

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        started = perf_counter()
        internal_result = self.run_internal_tool(context)
        external_result = self.run_external_tool(context)
        internal_runs = (
            internal_result.context_updates.get("q5_internal_execution_diagnosis", {}).get("module_runs", [])
            if isinstance(internal_result.context_updates, dict)
            else []
        )
        external_runs = (
            external_result.context_updates.get("q5_external_execution_diagnosis", {}).get("module_runs", [])
            if isinstance(external_result.context_updates, dict)
            else []
        )
        llm_output = {
            **internal_result.llm_output,
            **external_result.llm_output,
        }
        context_updates = {
            **internal_result.context_updates,
            **external_result.context_updates,
            "q5_execution_diagnosis": {
                "authenticity_status": "completed",
                "diagnosis_code": "separate_internal_external_lanes_saved",
                "module_runs": list(internal_runs) + list(external_runs),
                "elapsed_ms": int((perf_counter() - started) * 1000),
            },
        }
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q5 internal/external authorization LLM inputs and outputs saved separately.",
            llm_output=llm_output,
            context_updates=context_updates,
            proposals=list(internal_result.proposals) + list(external_result.proposals),
            confidence=0.75,
        )


def build_q5_what_am_i_allowed_to_do_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q5,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q5WhatAmIAllowedToDoPlugin:
    return Q5WhatAmIAllowedToDoPlugin(
        plugin_id=plugin_id,
        version=version,
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )


_Q4_INTERNAL_OBJECTIVE_FIELDS = (
    "objective_number",
    "objective_type",
    "capability_evidence_refs",
    "signal_or_gap_addressed",
    "objective_rationale",
    "candidate_description",
)

_Q4_EXTERNAL_OBJECTIVE_FIELDS = _Q4_INTERNAL_OBJECTIVE_FIELDS


def _project_internal_public_boundary(
    boundary: dict[str, Any],
    *,
    internal_llm_input: dict[str, Any],
) -> dict[str, Any]:
    public_boundary = deepcopy(boundary)
    allowed = public_boundary.get("allowed_internal_objectives_with_conditions")
    if allowed in (None, "", [], {}):
        public_boundary["allowed_internal_objectives_with_conditions"] = []
        return public_boundary
    if not isinstance(allowed, list):
        raise RuntimeError("q5_internal_public_projection_allowed_objectives_invalid")

    q4_candidates = _extract_q4_candidates_from_llm_input(internal_llm_input, lane="internal")
    projected_allowed = [
        _project_allowed_objective_with_q4_candidate(allowed_item, q4_candidates, public_boundary, lane="internal")
        for allowed_item in allowed
    ]
    public_boundary["allowed_internal_objectives_with_conditions"] = projected_allowed
    return public_boundary


def _project_external_public_boundary(
    boundary: dict[str, Any],
    *,
    external_llm_input: dict[str, Any],
) -> dict[str, Any]:
    public_boundary = deepcopy(boundary)
    allowed = public_boundary.get("allowed_external_objectives_with_conditions")
    if allowed in (None, "", [], {}):
        public_boundary["allowed_external_objectives_with_conditions"] = []
        return public_boundary
    if not isinstance(allowed, list):
        raise RuntimeError("q5_external_public_projection_allowed_objectives_invalid")

    q4_candidates = _extract_q4_candidates_from_llm_input(external_llm_input, lane="external")
    projected_allowed = [
        _project_allowed_objective_with_q4_candidate(allowed_item, q4_candidates, public_boundary, lane="external")
        for allowed_item in allowed
    ]
    public_boundary["allowed_external_objectives_with_conditions"] = projected_allowed
    return public_boundary


def _extract_q4_candidates_from_llm_input(llm_input: dict[str, Any], *, lane: str) -> list[dict[str, Any]]:
    model_context = llm_input.get("context") if isinstance(llm_input, dict) else {}
    prompt_context = model_context.get("context") if isinstance(model_context, dict) else {}
    
    if lane == "internal":
        q4_payload = prompt_context.get("Q4_InternalObjectiveCandidates")
    else:
        q4_payload = prompt_context.get("Q4_ExternalObjectiveCandidates")
        
    if isinstance(q4_payload, dict):
        candidate_set = q4_payload.get("candidate_set") or q4_payload
        candidates = candidate_set.get("objective_candidates") if isinstance(candidate_set, dict) else None
    else:
        candidates = None

    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError(f"q5_{lane}_public_projection_missing_q4_candidates")
    
    normalized: list[dict[str, Any]] = []
    fields = _Q4_INTERNAL_OBJECTIVE_FIELDS if lane == "internal" else _Q4_EXTERNAL_OBJECTIVE_FIELDS
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise RuntimeError(f"q5_{lane}_public_projection_q4_candidate_invalid")
        _require_q4_candidate_fields(candidate, fields=fields, lane=lane)
        normalized.append(candidate)
    return normalized


def _project_allowed_objective_with_q4_candidate(
    allowed_item: Any,
    q4_candidates: list[dict[str, Any]],
    boundary: dict[str, Any],
    *,
    lane: str,
) -> dict[str, Any]:
    if not isinstance(allowed_item, dict):
        raise RuntimeError(f"q5_{lane}_public_projection_allowed_objective_invalid")
    
    objective_number = str(allowed_item.get("objective_number") or "").strip()
    objective = str(allowed_item.get("objective") or "").strip()
    compliance_condition = str(allowed_item.get("compliance_condition") or "").strip()
    
    if not objective or not compliance_condition:
        raise RuntimeError(f"q5_{lane}_public_projection_allowed_objective_incomplete")

    # Match by objective_number first if available, otherwise by description
    if objective_number:
        matches = [c for c in q4_candidates if str(c.get("objective_number") or "").strip() == objective_number]
    else:
        matches = [c for c in q4_candidates if str(c.get("candidate_description") or "").strip() == objective]

    if len(matches) != 1:
        raise RuntimeError(f"q5_{lane}_public_projection_q4_candidate_match_failed")

    candidate = matches[0]
    return {
        "objective_number": str(candidate.get("objective_number") or "").strip(),
        "objective_type": str(candidate["objective_type"]).strip(),
        "capability_evidence_refs": _required_string_list(
            candidate.get("capability_evidence_refs"),
            error_code=f"q5_{lane}_public_projection_q4_candidate_incomplete:capability_evidence_refs",
        ),
        "signal_or_gap_addressed": str(candidate["signal_or_gap_addressed"]).strip(),
        "objective_rationale": str(candidate["objective_rationale"]).strip(),
        "candidate_description": str(candidate["candidate_description"]).strip(),
        "controlled_rules": _build_controlled_rules(compliance_condition, boundary, lane=lane),
    }


def _require_q4_candidate_fields(candidate: dict[str, Any], *, fields: tuple[str, ...], lane: str) -> None:
    missing_fields = [field for field in fields if field not in candidate]
    if missing_fields:
        raise RuntimeError(f"q5_{lane}_public_projection_q4_candidate_incomplete:{','.join(missing_fields)}")
    for field in (
        "objective_type",
        "signal_or_gap_addressed",
        "objective_rationale",
        "candidate_description",
    ):
        if not str(candidate.get(field) or "").strip():
            raise RuntimeError(f"q5_{lane}_public_projection_q4_candidate_incomplete:{field}")
    _required_string_list(
        candidate.get("capability_evidence_refs"),
        error_code=f"q5_{lane}_public_projection_q4_candidate_incomplete:capability_evidence_refs",
    )


def _build_controlled_rules(compliance_condition: str, boundary: dict[str, Any], *, lane: str) -> dict[str, Any]:
    condition = compliance_condition.strip()
    
    if lane == "internal":
        rule_refs = _required_string_list(
            [boundary.get("system_safety_boundary"), *list(boundary.get("non_bypassable_internal_constraints") or [])],
            error_code="q5_internal_public_projection_controlled_rules_missing:rule_refs",
        )
        non_bypassable_constraints = _string_list(boundary.get("non_bypassable_internal_constraints"))
        risk_refs = _string_list(
            [
                *list(boundary.get("identity_kernel_protection_hits") or []),
                *list(boundary.get("safety_module_protection_hits") or []),
                *list(boundary.get("supervision_module_protection_hits") or []),
                *list(boundary.get("memory_integrity_risks") or []),
                *list(boundary.get("continuity_risks") or []),
            ]
        )
    else: # external
        rule_refs = _required_string_list(
            boundary.get("system_safety_boundary"),
            error_code="q5_external_public_projection_controlled_rules_missing:rule_refs",
        )
        non_bypassable_constraints = _string_list(boundary.get("permission_boundary_hits"))
        risk_refs = _string_list(
            [
                *list(boundary.get("data_exfiltration_risks") or []),
                *list(boundary.get("unauthorized_mutation_risks") or []),
            ]
        )

    return {
        "source_compliance_condition": condition,
        "allowed_scope": condition,
        "mandatory_guardrails": [condition],
        "rule_refs": rule_refs,
        "non_bypassable_constraints": non_bypassable_constraints,
        "risk_refs": risk_refs,
    }


def _required_string_list(value: Any, *, error_code: str) -> list[str]:
    items = _string_list(value)
    if not items:
        raise RuntimeError(error_code)
    return items


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    raw_items = value if isinstance(value, list) else [value]
    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = str(raw or "").strip()
        if text and text not in seen:
            items.append(text)
            seen.add(text)
    return items
