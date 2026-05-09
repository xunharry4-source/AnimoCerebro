from __future__ import annotations

"""
Q3 (我是谁) evidence building and extraction.

Contains functions for building and extracting EVIDENCE_Q3 evidence.
"""

from typing import Any, Dict, List, Optional, Union

from zentex.web_console.contracts.nine_questions import (
    Q3PreprocessedEvidence,
    Q3WhatDoIHaveInferenceView,
    Q3AssetRow,
    Q3AgentRow,
    Q3WorkspaceAndPermission,
    Q3ToolsAndAgents,
    Q3MemoryAndStrategy,
    Q3ResourceSufficiencyView,
    Q2MissionBoundaryView,
    Q2RoleView,
)

from .helpers import _coerce_string_list


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_q3_prompt_modules(context_payload: dict[str, Any]) -> dict[str, Any]:
    candidates: list[object] = [
        context_payload.get("q3_prompt_modules"),
        context_payload.get("context_data"),
        context_payload.get("context"),
    ]
    for key in ("llm_trace_payload", "trace", "raw_trace_payload"):
        trace = context_payload.get(key)
        if isinstance(trace, dict):
            candidates.extend(
                [
                    trace.get("q3_prompt_modules"),
                    trace.get("context_data"),
                    trace.get("context"),
                ]
            )
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        modules = candidate.get("q3_prompt_modules") if isinstance(candidate.get("q3_prompt_modules"), dict) else candidate
        if isinstance(modules, dict) and isinstance(modules.get("upstream_llm_outputs"), dict):
            return modules
    return {}


def _extract_q3_prompt_evidence(context_payload: dict[str, Any]) -> dict[str, Any]:
    modules = _extract_q3_prompt_modules(context_payload)
    upstream = _dict_or_empty(modules.get("upstream_llm_outputs"))
    identity_binding = _dict_or_empty(modules.get("identity_binding"))
    q1_output = _dict_or_empty(upstream.get("q1_authoritative_llm_output"))
    q2_output = _dict_or_empty(upstream.get("q2_authoritative_llm_output"))
    identity_kernel = _dict_or_empty(identity_binding.get("identity_kernel_snapshot"))
    if not any((q1_output, q2_output, identity_kernel)):
        return {}
    return {
        "q1_environment_inference": q1_output,
        "q2_asset_inventory": q2_output,
        "identity_kernel_snapshot": identity_kernel,
    }


def _build_q3_preprocessed_evidence(context_payload: dict[str, Any]) -> Optional[Q3PreprocessedEvidence]:
    prompt_evidence = _extract_q3_prompt_evidence(context_payload)
    q1_environment_inference = (
        context_payload.get("q1_environment_inference")
        or context_payload.get("workspace_domain_inference")
        or prompt_evidence.get("q1_environment_inference")
        or {}
    )
    q2_asset_inventory = (
        context_payload.get("q2_asset_inventory")
        or prompt_evidence.get("q2_asset_inventory")
        or {}
    )
    identity_kernel_snapshot = (
        context_payload.get("identity_kernel_snapshot")
        if isinstance(context_payload.get("identity_kernel_snapshot"), dict)
        else prompt_evidence.get("identity_kernel_snapshot")
        if isinstance(prompt_evidence.get("identity_kernel_snapshot"), dict)
        else {}
    )
    if isinstance(q1_environment_inference, dict) and isinstance(q2_asset_inventory, dict) and (q1_environment_inference or q2_asset_inventory or identity_kernel_snapshot):
        return Q3PreprocessedEvidence(
            workspace_permission=Q3WorkspaceAndPermission(),
            tools_agents=Q3ToolsAndAgents(),
            memory_strategy=Q3MemoryAndStrategy(),
            asset_inventory={},
            q1_environment_inference=q1_environment_inference,
            q2_asset_inventory=q2_asset_inventory,
            q1_llm_trace_payload=context_payload.get("q1_llm_trace_payload")
            if isinstance(context_payload.get("q1_llm_trace_payload"), dict)
            else {},
            q2_llm_trace_payload=context_payload.get("q2_llm_trace_payload")
            if isinstance(context_payload.get("q2_llm_trace_payload"), dict)
            else {},
            identity_kernel_snapshot=identity_kernel_snapshot,
        )

    return None


def _extract_q3_preprocessed_evidence(context_payload: object) -> Optional[Q3PreprocessedEvidence]:
    if not isinstance(context_payload, dict):
        return None
    if not any(
        k in context_payload
        for k in (
            "workspaces_and_permissions",
            "q1_environment_inference",
            "q2_asset_inventory",
            "q1_llm_trace_payload",
            "q2_llm_trace_payload",
            "q3_role_profile",
            "q3_mission_boundary",
            "llm_trace_payload",
            "q3_prompt_modules",
        )
    ):
        return None
    return _build_q3_preprocessed_evidence(context_payload)


def _extract_q3_inference_result(result_payload: object) -> Optional[Q3WhatDoIHaveInferenceView]:
    if not isinstance(result_payload, dict):
        return None

    q3_result = result_payload.get("Q3InferenceResult") if isinstance(result_payload.get("Q3InferenceResult"), dict) else {}
    role_profile_raw = q3_result.get("RoleProfile") or result_payload.get("q3_role_profile")
    mission_boundary_raw = q3_result.get("MissionContinuityBoundary") or result_payload.get("q3_mission_boundary")
    context_updates = result_payload.get("context_updates") if isinstance(result_payload.get("context_updates"), dict) else {}
    if (not isinstance(role_profile_raw, dict) or not isinstance(mission_boundary_raw, dict)) and isinstance(context_updates, dict):
        role_profile_raw = context_updates.get("q3_role_profile")
        mission_boundary_raw = context_updates.get("q3_mission_boundary")
    if isinstance(result_payload.get("proposals"), list):
        for proposal in result_payload.get("proposals") or []:
            if not isinstance(proposal, dict):
                continue
            kind = str(proposal.get("kind") or "").strip()
            if kind == "role_profile":
                role_profile_raw = proposal
            elif kind == "mission_continuity_boundary":
                mission_boundary_raw = proposal
    if isinstance(role_profile_raw, dict) and isinstance(mission_boundary_raw, dict):
        return Q3WhatDoIHaveInferenceView(
            role_profile=Q2RoleView(
                identity_role=str(role_profile_raw.get("identity_role") or ""),
                active_role=str(role_profile_raw.get("active_role") or ""),
                inferred_reference_role=str(role_profile_raw.get("inferred_reference_role") or ""),
                role_alignment_gap=str(role_profile_raw.get("role_alignment_gap") or ""),
                task_role=str(role_profile_raw.get("task_role") or ""),
            ),
            mission_boundary=Q2MissionBoundaryView(
                current_mission=str(mission_boundary_raw.get("current_mission") or ""),
                priority_duties=_coerce_string_list(mission_boundary_raw.get("priority_duties")),
                continuity_boundaries=_coerce_string_list(mission_boundary_raw.get("continuity_boundaries")),
            ),
        )

    return None
