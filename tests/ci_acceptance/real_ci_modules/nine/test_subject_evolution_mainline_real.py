from __future__ import annotations

from pathlib import Path

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.nine_questions.subject_evolution_mainline import (
    G41AgendaItem,
    G41CognitiveToolSpec,
    G41MainlineRuntime,
)


def _tool_payload(suffix: str, tool_id: str, *, blocked: bool = False) -> dict:
    return {
        "tool_id": f"{tool_id}-{suffix}",
        "name": f"{tool_id} tool",
        "tool_type": "risk_comparator",
        "purpose": "Compare G41 objective risks without side effects.",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "required_context": ["nine_question_objective_context"],
        "trigger_conditions": ["q8_profile_ready"],
        "do_not_use_when": ["external_execution_requested"] if blocked else ["secret_boundary_active"],
        "read_only": True,
        "side_effect_free": True,
        "execution_permissions": [],
        "lifecycle_status": "active",
    }


def test_subject_evolution_business_enforces_read_only_tools_attention_only_agenda_and_isolated_patch(tmp_path: Path) -> None:
    suffix = unique_suffix()
    runtime = G41MainlineRuntime(base_dir=tmp_path)

    selected_registration = runtime.register_tool(G41CognitiveToolSpec(**_tool_payload(suffix, "selected")))
    blocked_registration = runtime.register_tool(G41CognitiveToolSpec(**_tool_payload(suffix, "blocked", blocked=True)))

    queried_tools = runtime.list_tools()
    assert [row.spec.tool_id for row in queried_tools] == [
        selected_registration.spec.tool_id,
        blocked_registration.spec.tool_id,
    ]

    plan = runtime.build_invocation_plan(
        target_phase="decision_synthesis",
        context={
            "nine_question_objective_context": {"profile_status": "ready"},
            "available_conditions": ["q8_profile_ready"],
            "blocked_conditions": ["external_execution_requested"],
        },
    )
    assert plan.selected_tool_ids == [selected_registration.spec.tool_id]
    assert blocked_registration.spec.tool_id in plan.blocked_tool_reasons
    assert plan.read_only is True
    assert plan.side_effect_free is True
    assert plan.execution_attempted is False
    assert plan.serial_steps == [selected_registration.spec.tool_id]

    agenda = runtime.add_agenda_item(
        G41AgendaItem(
            title=f"recheck objective drift {suffix}",
            reason="Q8 and Q9 changed under medium risk.",
            source_question_ids=["q8", "q9"],
            reminder_conditions=["objective_drift_detected"],
        )
    )
    queried_agenda = runtime.list_agenda()
    assert queried_agenda[0].item_id == agenda.item_id
    assert queried_agenda[0].external_action_allowed is False

    decisions = runtime.evaluate_agenda({"attention_signals": ["objective_drift_detected"]})
    assert decisions[0].item_id == agenda.item_id
    assert decisions[0].should_revisit is True
    assert decisions[0].result == "attention_only"
    assert decisions[0].external_action_attempted is False

    patch = runtime.create_candidate_patch(
        {
            "source_gap_id": f"gap-{suffix}",
            "target_component": "cognitive_tool_registry",
            "failure_patterns": ["missing_counterfactual_compare_tool"],
            "proposed_files": ["src/zentex/plugins/counterfactual_compare.py"],
            "rollback_conditions": ["verification_fails", "g25_rejects_candidate"],
            "validation_requirements": ["manifest_exists", "read_only_contract"],
        }
    )
    queried_patch = runtime.get_candidate_patch(patch.patch_id)
    assert queried_patch.patch_id == patch.patch_id
    assert queried_patch.writes_to_mainline is False
    assert queried_patch.promoted is False
    assert Path(queried_patch.manifest_path).exists()
    assert Path(queried_patch.manifest_path).is_relative_to(tmp_path)

    verification = runtime.verify_candidate_patch(patch.patch_id)
    assert verification.status == "pass"
    assert verification.checked_manifest_exists is True
    assert verification.checked_isolation_path_exists is True
    assert verification.checked_no_mainline_write is True
    assert verification.evidence_refs == [queried_patch.manifest_path, queried_patch.isolation_path]


def test_subject_evolution_brain_organ_map_business_returns_exact_b1_to_b8_pure_cognitive_boundaries(
    tmp_path: Path,
) -> None:
    runtime = G41MainlineRuntime(base_dir=tmp_path)

    organ_map = runtime.get_brain_organ_map()
    assert organ_map.organ_count == 8
    assert organ_map.organ_ids == ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]
    assert organ_map.pure_cognitive_layer is True
    assert organ_map.direct_host_control_allowed is False
    assert organ_map.external_action_allowed is False
    assert organ_map.execution_permissions_present is False
    assert organ_map.required_integration_refs == ["G31A", "G17", "G25", "G41"]

    by_id = {organ.organ_id: organ for organ in organ_map.organs}
    assert by_id["B1"].implementation_refs == ["zentex.kernel.state_domain.working_memory.WorkingMemoryController"]
    assert by_id["B2"].implementation_refs == [
        "zentex.kernel.state_domain.self_model.SelfModelEngine",
        "zentex.reflection.living_self_model",
    ]
    assert by_id["B3"].implementation_refs == ["zentex.kernel.state_domain.temporal.CognitiveTemporalEngine"]
    assert by_id["B4"].implementation_refs == [
        "zentex.kernel.thought_sandbox",
        "zentex.cognition.simulation",
    ]
    assert by_id["B5"].implementation_refs == ["zentex.safety.conflict_engine.CognitiveConflictEngine"]
    assert by_id["B6"].implementation_refs == [
        "zentex.cognition.theory_of_mind",
        "zentex.cognition.social_mind",
    ]
    assert by_id["B7"].implementation_refs == [
        "zentex.kernel.flow_domain.think_loop",
        "zentex.nine_questions.subject_evolution_mainline.G41MainlineRuntime",
    ]
    assert by_id["B8"].implementation_refs == ["zentex.memory.consolidation.consolidation.ConsolidationEngine"]

    for organ in organ_map.organs:
        assert organ.overview_status == "implemented"
        assert organ.pure_cognitive_layer is True
        assert organ.direct_host_control_allowed is False
        assert organ.external_action_allowed is False
        assert organ.execution_permissions == []
        assert organ.boundary_notes, f"{organ.organ_id} must explain its boundary"

    b6 = runtime.get_brain_organ("b6")
    assert b6.organ_id == "B6"
    assert "G23" in b6.integration_refs

    purity = runtime.verify_brain_organ_purity()
    assert purity.status == "pass"
    assert purity.checked_organ_ids == organ_map.organ_ids
    assert purity.violations == []


def test_subject_evolution_api_uses_requests_and_read_after_write_checks_tools_agenda_and_patch(
    acceptance_app: FastAPI,
    tmp_path: Path,
) -> None:
    suffix = unique_suffix()
    acceptance_app.state.subject_evolution_runtime = G41MainlineRuntime(base_dir=tmp_path)

    with live_http_server(acceptance_app) as base_url:
        first_tool = _tool_payload(suffix, "api-selected")
        second_tool = _tool_payload(suffix, "api-blocked", blocked=True)
        first_response = requests.post(f"{base_url}/api/web/g41/tools", json=first_tool, timeout=10)
        second_response = requests.post(f"{base_url}/api/web/g41/tools", json=second_tool, timeout=10)
        assert first_response.status_code == 200, first_response.text
        assert second_response.status_code == 200, second_response.text

        invalid_tool = dict(first_tool)
        invalid_tool["tool_id"] = f"api-invalid-{suffix}"
        invalid_tool["read_only"] = False
        invalid_response = requests.post(f"{base_url}/api/web/g41/tools", json=invalid_tool, timeout=10)
        assert invalid_response.status_code == 422
        assert "read_only=True" in invalid_response.text

        tools_query = requests.get(f"{base_url}/api/web/g41/tools", timeout=10)
        assert tools_query.status_code == 200
        tools_payload = tools_query.json()
        assert [row["spec"]["tool_id"] for row in tools_payload] == [
            first_tool["tool_id"],
            second_tool["tool_id"],
        ]

        plan_response = requests.post(
            f"{base_url}/api/web/g41/tool-plans",
            json={
                "target_phase": "decision_synthesis",
                "context": {
                    "nine_question_objective_context": {"profile_status": "ready"},
                    "available_conditions": ["q8_profile_ready"],
                    "blocked_conditions": ["external_execution_requested"],
                },
            },
            timeout=10,
        )
        assert plan_response.status_code == 200
        plan_payload = plan_response.json()
        assert plan_payload["selected_tool_ids"] == [first_tool["tool_id"]]
        assert second_tool["tool_id"] in plan_payload["blocked_tool_reasons"]
        assert plan_payload["execution_attempted"] is False

        agenda_response = requests.post(
            f"{base_url}/api/web/g41/agenda/items",
            json={
                "title": f"API recheck G41 agenda {suffix}",
                "reason": "Objective changed after Q8/Q9 export.",
                "source_question_ids": ["q8", "q9"],
                "reminder_conditions": ["objective_drift_detected"],
                "external_action_allowed": False,
            },
            timeout=10,
        )
        assert agenda_response.status_code == 200, agenda_response.text
        agenda_payload = agenda_response.json()
        agenda_query = requests.get(f"{base_url}/api/web/g41/agenda/items", timeout=10)
        assert agenda_query.status_code == 200
        assert agenda_query.json()[0]["item_id"] == agenda_payload["item_id"]

        agenda_eval = requests.post(
            f"{base_url}/api/web/g41/agenda/evaluate",
            json={"context": {"attention_signals": ["objective_drift_detected"]}},
            timeout=10,
        )
        assert agenda_eval.status_code == 200
        agenda_decision = agenda_eval.json()[0]
        assert agenda_decision["should_revisit"] is True
        assert agenda_decision["result"] == "attention_only"
        assert agenda_decision["external_action_attempted"] is False

        patch_response = requests.post(
            f"{base_url}/api/web/g41/candidate-patches",
            json={
                "source_gap_id": f"api-gap-{suffix}",
                "target_component": "subject_evolution_cognitive_tool_orchestrator",
                "failure_patterns": ["selected_tools_not_planned"],
                "proposed_files": ["src/zentex/plugins/subject_evolution_candidate.py"],
                "rollback_conditions": ["sandbox_verification_fails"],
                "validation_requirements": ["manifest_exists", "no_mainline_write"],
            },
            timeout=10,
        )
        assert patch_response.status_code == 200, patch_response.text
        patch_payload = patch_response.json()

        patch_query = requests.get(
            f"{base_url}/api/web/g41/candidate-patches/{patch_payload['patch_id']}",
            timeout=10,
        )
        assert patch_query.status_code == 200
        queried_patch = patch_query.json()
        assert queried_patch["patch_id"] == patch_payload["patch_id"]
        assert queried_patch["writes_to_mainline"] is False
        assert queried_patch["promoted"] is False
        assert Path(queried_patch["manifest_path"]).exists()

        verification_response = requests.post(
            f"{base_url}/api/web/g41/candidate-patches/{patch_payload['patch_id']}/verify",
            timeout=10,
        )
        assert verification_response.status_code == 200
        verification_payload = verification_response.json()
        assert verification_payload["status"] == "pass"
        assert verification_payload["checked_no_mainline_write"] is True
        assert verification_payload["evidence_refs"] == [
            queried_patch["manifest_path"],
            queried_patch["isolation_path"],
        ]

        audit_response = requests.get(f"{base_url}/api/web/g41/audit", timeout=10)
        assert audit_response.status_code == 200
        audit_types = [row["event_type"] for row in audit_response.json()]
        assert "tool_registered" in audit_types
        assert "tool_plan_built" in audit_types
        assert "agenda_evaluated" in audit_types
        assert "candidate_patch_verified" in audit_types


def test_subject_evolution_brain_organ_map_api_uses_requests_and_checks_exact_query_results(
    acceptance_app: FastAPI,
    tmp_path: Path,
) -> None:
    acceptance_app.state.subject_evolution_runtime = G41MainlineRuntime(base_dir=tmp_path)

    with live_http_server(acceptance_app) as base_url:
        map_response = requests.get(f"{base_url}/api/web/g41/brain-organs", timeout=10)
        assert map_response.status_code == 200
        organ_map = map_response.json()
        assert organ_map["organ_count"] == 8
        assert organ_map["organ_ids"] == ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]
        assert organ_map["pure_cognitive_layer"] is True
        assert organ_map["direct_host_control_allowed"] is False
        assert organ_map["external_action_allowed"] is False
        assert organ_map["execution_permissions_present"] is False
        assert organ_map["required_integration_refs"] == ["G31A", "G17", "G25", "G41"]

        organs_by_id = {organ["organ_id"]: organ for organ in organ_map["organs"]}
        assert organs_by_id["B4"]["implementation_refs"] == [
            "zentex.kernel.thought_sandbox",
            "zentex.cognition.simulation",
        ]
        assert organs_by_id["B6"]["implementation_refs"] == [
            "zentex.cognition.theory_of_mind",
            "zentex.cognition.social_mind",
        ]
        assert organs_by_id["B8"]["implementation_refs"] == [
            "zentex.memory.consolidation.consolidation.ConsolidationEngine"
        ]
        for organ in organ_map["organs"]:
            assert organ["overview_status"] == "implemented"
            assert organ["pure_cognitive_layer"] is True
            assert organ["direct_host_control_allowed"] is False
            assert organ["external_action_allowed"] is False
            assert organ["execution_permissions"] == []

        b7_response = requests.get(f"{base_url}/api/web/g41/brain-organs/B7", timeout=10)
        assert b7_response.status_code == 200
        b7 = b7_response.json()
        assert b7["organ_id"] == "B7"
        assert b7["name"] == "Meta-cognition scheduler"
        assert "G17" in b7["integration_refs"]
        assert "G25" in b7["integration_refs"]
        assert b7["external_action_allowed"] is False

        missing_response = requests.get(f"{base_url}/api/web/g41/brain-organs/B9", timeout=10)
        assert missing_response.status_code == 404
        assert missing_response.json()["detail"]["error"] == "subject_evolution_brain_organ_not_found"

        purity_response = requests.get(f"{base_url}/api/web/g41/brain-organs/purity", timeout=10)
        assert purity_response.status_code == 200
        purity = purity_response.json()
        assert purity["status"] == "pass"
        assert purity["checked_organ_ids"] == organ_map["organ_ids"]
        assert purity["violations"] == []

        audit_response = requests.get(f"{base_url}/api/web/g41/audit", timeout=10)
        assert audit_response.status_code == 200
        audit_events = audit_response.json()
        assert audit_events[-1]["event_type"] == "brain_organ_purity_verified"
        assert audit_events[-1]["metadata"]["status"] == "pass"
