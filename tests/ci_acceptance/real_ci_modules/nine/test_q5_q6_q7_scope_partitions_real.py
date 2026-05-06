from __future__ import annotations

from plugins.nine_questions.scope_partition import (
    build_q5_internal_external_partition,
    build_q6_internal_external_partition,
    build_q7_internal_external_partition,
    classify_scope,
    partition_items,
)
from zentex.web_console.routers.nine_questions_impl.evidence_q5 import _extract_q5_inference_result
from zentex.web_console.routers.nine_questions_impl.evidence_q6 import _extract_q6_inference_result
from zentex.web_console.routers.nine_questions_impl.evidence_q7 import _extract_q7_inference_result


def test_q5_q6_q7_internal_external_profiles_split_real_outputs() -> None:
    q5_partition = build_q5_internal_external_partition(
        authorization_profile={
            "allowed_action_space": [
                "write internal reflection summary",
                {"action": "publish via Reddit connector", "action_scope": "external"},
            ],
            "forbidden_action_space": [
                {"action": "modify internal audit ledger", "reason": "audit integrity"},
                {"action": "send credentials to external API", "reason": "secret leakage"},
            ],
            "requires_escalation_actions": [
                "internal schema migration review",
                {"action": "delegate to agent:devops", "target_id": "agent:devops"},
            ],
            "contact_and_org_boundaries": {"interaction_scope": "whitelist_only"},
        },
        permission_boundary={
            "authorized_actions": ["write internal reflection summary", "publish via Reddit connector"],
            "unauthorized_actions": ["modify internal audit ledger", "send credentials to external API"],
            "conditional_actions": ["internal schema migration review", "delegate to agent:devops"],
        },
    )
    assert q5_partition["q5_internal_authorization_boundary_profile"]["allowed_action_space"] == [
        "write internal reflection summary"
    ]
    assert q5_partition["q5_external_authorization_boundary_profile"]["allowed_action_space"] == [
        {"action": "publish via Reddit connector", "action_scope": "external"}
    ]
    assert q5_partition["q5_external_permission_boundary"]["conditional_actions"] == [
        "delegate to agent:devops"
    ]

    q6_partition = build_q6_internal_external_partition(
        forbidden_zone_profile={
            "absolute_red_lines": [
                "do not corrupt internal memory records",
                "do not send credentials to an external API",
            ],
            "performance_tradeoff_bans": ["do not skip internal audit"],
            "prohibited_strategies": ["do not use external browser session without consent"],
            "contamination_risks": ["internal identity pollution", "third-party token leakage"],
        }
    )
    assert q6_partition["q6_internal_forbidden_zone_profile"]["absolute_red_lines"] == [
        "do not corrupt internal memory records"
    ]
    assert q6_partition["q6_external_forbidden_zone_profile"]["absolute_red_lines"] == [
        "do not send credentials to an external API"
    ]
    assert q6_partition["q6_external_forbidden_zone_profile"]["contamination_risks"] == [
        "third-party token leakage"
    ]

    q7_partition = build_q7_internal_external_partition(
        alternative_strategy_profile={
            "fallback_plans": [
                "create internal follow-up task",
                {"title": "ask CLI connector for file inspection", "executor_type": "cli"},
            ],
            "degradation_strategies": ["switch to internal read-only mode"],
            "collaboration_switches": ["delegate to agent:research"],
            "exploratory_actions": ["inspect internal audit trail", "query GitHub issue API"],
        }
    )
    assert q7_partition["q7_internal_alternative_strategy_profile"]["fallback_plans"] == [
        "create internal follow-up task"
    ]
    assert q7_partition["q7_external_alternative_strategy_profile"]["fallback_plans"] == [
        {"title": "ask CLI connector for file inspection", "executor_type": "cli"}
    ]
    assert q7_partition["q7_external_alternative_strategy_profile"]["exploratory_actions"] == [
        "query GitHub issue API"
    ]


def test_scope_partition_explicit_scope_overrides_keyword_text_real() -> None:
    assert classify_scope({"title": "internal wording through CLI", "task_scope": "external"}) == "external"
    assert classify_scope({"title": "external wording retained for internal audit", "scope": "internal"}) == "internal"
    split = partition_items(
        [
            {"title": "external connector read", "scope": "internal"},
            {"title": "plain internal learning"},
            {"title": "call mcp:notion", "target_id": "mcp:notion"},
        ]
    )
    assert [item["title"] for item in split["internal"]] == [
        "external connector read",
        "plain internal learning",
    ]
    assert [item["title"] for item in split["external"]] == ["call mcp:notion"]


def test_scope_partition_empty_and_web_inference_readback_real() -> None:
    assert partition_items(None) == {"internal": [], "external": []}
    assert build_q6_internal_external_partition(forbidden_zone_profile={})["q6_external_forbidden_zone_profile"] == {
        "absolute_red_lines": [],
        "performance_tradeoff_bans": [],
        "prohibited_strategies": [],
        "contamination_risks": [],
    }

    q5_view = _extract_q5_inference_result(
        {
            "authorization_boundary_profile": {
                "allowed_action_space": ["write internal reflection"],
                "forbidden_action_space": [],
                "requires_escalation_actions": [],
            },
            "q5_internal_authorization_boundary_profile": {"allowed_action_space": ["write internal reflection"]},
            "q5_external_authorization_boundary_profile": {"allowed_action_space": []},
            "q5_internal_permission_boundary": {"authorized_actions": ["write internal reflection"]},
            "q5_external_permission_boundary": {"authorized_actions": []},
        }
    )
    assert q5_view is not None
    assert q5_view.internal_authorization_boundary_profile["allowed_action_space"] == [
        "write internal reflection"
    ]

    q6_view = _extract_q6_inference_result(
        {
            "q6_forbidden_zone_profile": {"absolute_red_lines": ["do not leak secrets"]},
            "q6_internal_forbidden_zone_profile": {"absolute_red_lines": []},
            "q6_external_forbidden_zone_profile": {"absolute_red_lines": ["do not leak secrets"]},
        }
    )
    assert q6_view is not None
    assert q6_view.external_forbidden_zone_profile["absolute_red_lines"] == ["do not leak secrets"]

    q7_view = _extract_q7_inference_result(
        {
            "q7_alternative_strategy_profile": {
                "fallback_plans": ["create internal follow-up"],
                "degradation_strategies": [],
                "collaboration_switches": ["delegate to agent:research"],
                "exploratory_actions": [],
            },
            "q7_internal_alternative_strategy_profile": {"fallback_plans": ["create internal follow-up"]},
            "q7_external_alternative_strategy_profile": {"collaboration_switches": ["delegate to agent:research"]},
        }
    )
    assert q7_view is not None
    assert q7_view.external_alternative_strategy_profile["collaboration_switches"] == [
        "delegate to agent:research"
    ]
