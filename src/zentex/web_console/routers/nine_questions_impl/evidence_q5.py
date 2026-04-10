"""
Q5 (我被允许做什么) evidence extraction.

Contains functions for building and extracting EVIDENCE_Q5 evidence.
"""

from typing import Any, Dict, List, Optional

from zentex.web_console.contracts.nine_questions import (
    Q5PreprocessedEvidence,
    Q5WhatAmIAllowedToDoInferenceView,
)

from .helpers import _coerce_string_list


def _extract_q5_preprocessed_evidence(context_payload: object) -> Q5PreprocessedEvidence | None:
    if not isinstance(context_payload, dict):
        return None

    def _flatten_policy_lines(value: object) -> list[str]:
        if isinstance(value, dict):
            lines: list[str] = []
            for key, raw in value.items():
                if raw is None:
                    continue
                if isinstance(raw, list):
                    rendered = ", ".join(str(item) for item in raw)
                elif isinstance(raw, bool):
                    rendered = str(raw).lower()
                else:
                    rendered = str(raw)
                lines.append(f"{key}={rendered}")
            return lines
        return _coerce_string_list(value)

    q4_profile = context_payload.get("q4_capability_boundary_profile")
    action_space = _coerce_string_list(context_payload.get("actionable_space"))
    if not action_space and isinstance(q4_profile, dict):
        action_space = _coerce_string_list(q4_profile.get("actionable_space"))

    boundaries = _coerce_string_list(context_payload.get("tenant_boundaries"))
    if not boundaries:
        boundaries = _flatten_policy_lines(context_payload.get("tenant_scope"))

    contact_policy = _flatten_policy_lines(context_payload.get("contact_policy"))

    trust = context_payload.get("agent_trust_status") or {}
    if not isinstance(trust, dict):
        trust = {}
    if not trust and isinstance(context_payload.get("q3_connected_agents"), list):
        derived_trust: dict[str, str] = {}
        for raw_agent in context_payload.get("q3_connected_agents", []):
            if not isinstance(raw_agent, dict):
                continue
            agent_id = raw_agent.get("agent_id") or raw_agent.get("id") or raw_agent.get("name")
            agent_status = raw_agent.get("trust_level") or raw_agent.get("status") or raw_agent.get("scope")
            if agent_id and agent_status:
                derived_trust[str(agent_id)] = str(agent_status)
        trust = derived_trust

    if not action_space and not boundaries and not contact_policy and not trust:
        return None
    return Q5PreprocessedEvidence(
        actionable_space=action_space,
        contact_policy=contact_policy,
        tenant_boundaries=boundaries,
        agent_trust_status={str(k): str(v) for k, v in trust.items()} if isinstance(trust, dict) else {},
    )


def _extract_q5_inference_result(result_payload: object) -> Q5WhatAmIAllowedToDoInferenceView | None:
    if not isinstance(result_payload, dict):
        return None
    profile = result_payload.get("authorization_boundary_profile") if isinstance(result_payload.get("authorization_boundary_profile"), dict) else result_payload
    if not isinstance(profile, dict):
        return None

    contact_boundaries = profile.get("contact_and_org_boundaries")
    if not isinstance(contact_boundaries, dict):
        contact_boundaries = {}

    forbidden_payload = profile.get("forbidden_action_space")
    forbidden_actions: list[str] = []
    compliance_risks = _coerce_string_list(profile.get("compliance_risks"))
    if isinstance(forbidden_payload, list):
        for raw_item in forbidden_payload:
            if isinstance(raw_item, dict):
                action = str(raw_item.get("action") or "").strip()
                reason = str(raw_item.get("reason") or "").strip()
                if action and reason:
                    forbidden_actions.append(f"{action}: {reason}")
                    compliance_risks.append(reason)
                elif action:
                    forbidden_actions.append(action)
            elif raw_item is not None:
                forbidden_actions.append(str(raw_item))

    forbidden_actions.extend(_coerce_string_list(profile.get("explicitly_forbidden_actions")))
    seen_forbidden: set[str] = set()
    forbidden_actions = [item for item in forbidden_actions if item and not (item in seen_forbidden or seen_forbidden.add(item))]

    compliance_risks.extend(_coerce_string_list(profile.get("requires_escalation_actions")))
    seen_risks: set[str] = set()
    compliance_risks = [item for item in compliance_risks if item and not (item in seen_risks or seen_risks.add(item))]

    allowed_targets = _coerce_string_list(profile.get("allowed_delegation_targets"))
    if not allowed_targets:
        allowed_targets = _coerce_string_list(contact_boundaries.get("allowed_delegation_targets"))

    execution_tier = str(profile.get("execution_tier") or contact_boundaries.get("execution_tier") or "unknown")
    interaction_scope = str(profile.get("interaction_scope") or contact_boundaries.get("interaction_scope") or "unknown")
    requires_human_confirmation = bool(
        profile.get("requires_human_confirmation")
        if "requires_human_confirmation" in profile
        else contact_boundaries.get("requires_human_confirmation")
    )
    requires_cloud_audit = bool(
        profile.get("requires_cloud_audit")
        if "requires_cloud_audit" in profile
        else contact_boundaries.get("requires_cloud_audit")
    )

    if not any(
        (
            execution_tier != "unknown",
            interaction_scope != "unknown",
            requires_human_confirmation,
            requires_cloud_audit,
            bool(forbidden_actions),
            bool(compliance_risks),
            bool(allowed_targets),
        )
    ):
        return None

    return Q5WhatAmIAllowedToDoInferenceView(
        execution_tier=execution_tier,
        interaction_scope=interaction_scope,
        requires_human_confirmation=requires_human_confirmation,
        requires_cloud_audit=requires_cloud_audit,
        explicitly_forbidden_actions=forbidden_actions,
        compliance_risks=compliance_risks,
        allowed_delegation_targets=allowed_targets,
    )



