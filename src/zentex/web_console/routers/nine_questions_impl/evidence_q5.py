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
    if not action_space:
        authorization_baseline = context_payload.get("q5_authorization_baseline")
        if isinstance(authorization_baseline, dict):
            action_space = _coerce_string_list(authorization_baseline.get("allowed_action_space"))

    boundaries = _coerce_string_list(context_payload.get("tenant_boundaries"))
    if not boundaries:
        boundaries = _flatten_policy_lines(context_payload.get("tenant_scope"))
    if not boundaries:
        authorization_baseline = context_payload.get("q5_authorization_baseline")
        if isinstance(authorization_baseline, dict):
            boundaries = _flatten_policy_lines(
                (authorization_baseline.get("contact_and_org_boundaries") or {}).get("tenant_scope")
            )

    contact_policy = _flatten_policy_lines(context_payload.get("contact_policy"))
    if not contact_policy:
        authorization_baseline = context_payload.get("q5_authorization_baseline")
        if isinstance(authorization_baseline, dict):
            contact_policy = _flatten_policy_lines(
                (authorization_baseline.get("contact_and_org_boundaries") or {}).get("contact_policy")
            )

    trust = context_payload.get("q5_agent_trust_status") or context_payload.get("agent_trust_status") or {}
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
    # Q5 plugin 写入 context_updates 的是 q5_authorization_boundary_profile（直接是 profile dict）
    # 也可能整个 result_payload 就是 profile
    profile = result_payload.get("authorization_boundary_profile")
    if not isinstance(profile, dict):
        profile = result_payload  # compatibility path: 整个 payload 直接就是 profile
    if not isinstance(profile, dict):
        return None

    # 从 contact_and_org_boundaries 提取组织边界信息
    contact_boundaries = profile.get("contact_and_org_boundaries")
    if not isinstance(contact_boundaries, dict):
        contact_boundaries = {}

    # allowed_action_space → allowed_delegation_targets（最接近的映射）
    allowed_delegation_targets = _coerce_string_list(
        profile.get("allowed_action_space")
        or contact_boundaries.get("allowed_delegation_targets")
    )

    # forbidden_action_space → explicitly_forbidden_actions
    forbidden_payload = profile.get("forbidden_action_space") or []
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
    compliance_risks.extend(_coerce_string_list(profile.get("requires_escalation_actions")))

    # 去重
    seen: set[str] = set()
    forbidden_actions = [x for x in forbidden_actions if x and not (x in seen or seen.add(x))]
    seen2: set[str] = set()
    compliance_risks = [x for x in compliance_risks if x and not (x in seen2 or seen2.add(x))]

    # 从 contact_and_org_boundaries 推断 execution_tier / interaction_scope
    execution_tier = str(
        contact_boundaries.get("execution_tier")
        or profile.get("execution_tier")
        or ("read_only" if not profile.get("allowed_action_space") else "constrained_execute")
    )
    interaction_scope = str(
        contact_boundaries.get("interaction_scope")
        or profile.get("interaction_scope")
        or "whitelist_only"
    )
    requires_human_confirmation = bool(
        contact_boundaries.get("requires_human_confirmation")
        or profile.get("requires_human_confirmation")
        or bool(profile.get("requires_escalation_actions"))
    )
    requires_cloud_audit = bool(
        contact_boundaries.get("requires_cloud_audit")
        or profile.get("requires_cloud_audit")
        or False
    )

    if not any((forbidden_actions, compliance_risks, allowed_delegation_targets,
                execution_tier not in ("unknown", ""), interaction_scope not in ("unknown", ""))):
        return None

    return Q5WhatAmIAllowedToDoInferenceView(
        execution_tier=execution_tier,
        interaction_scope=interaction_scope,
        requires_human_confirmation=requires_human_confirmation,
        requires_cloud_audit=requires_cloud_audit,
        explicitly_forbidden_actions=forbidden_actions,
        compliance_risks=compliance_risks,
        allowed_delegation_targets=allowed_delegation_targets,
    )

