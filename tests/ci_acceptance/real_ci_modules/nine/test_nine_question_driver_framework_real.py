from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import requests
from fastapi import FastAPI

from zentex.nine_questions.question_driver_framework import QUESTION_DRIVER_SPECS
from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _context_and_result(question_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    q1_result = {
        "workspace_domain_inference": {
            "primary_domain": "software_engineering",
            "secondary_domains": ["testing", "plugin_governance"],
            "confidence": 0.93,
            "reasoning_summary": "Workspace contains Zentex runtime, API routers, and CI tests.",
            "uncertainties": ["production LLM availability is environment-dependent"],
            "suggested_first_step": "Verify nine-question APIs through requests.",
        }
    }
    contexts: dict[str, dict[str, Any]] = {
        "q1": {
            "physical_host_state": {"cwd": "/workspace", "platform": "darwin", "memory_pressure": "normal"},
            "environment_event": {"kind": "acceptance", "summary": "feature 44 real API verification"},
            "workspace_structure_analysis": {
                "directory_hierarchy_summary": "src and tests are present",
                "top_level_dirs": ["src", "tests"],
                "file_total_count": 44,
                "suffix_distribution": {".py": 33, ".md": 11},
                "candidate_groups": ["zentex"],
            },
            "workspace_content_samples": {
                "sampled_file_summaries": [{"path": "Zentex_产品功能文档-v1.md", "summary": "feature 44 spec"}],
                "log_anomaly_snippets": ["no fake tests allowed"],
            },
        },
        "q2": {
            "workspace_domain_inference": q1_result["workspace_domain_inference"],
            "identity_core": {
                "meta_motivation": "complete real implementation",
                "values_prohibition": "no mock, no hidden errors",
                "non_bypassable_constraints": ["service.py stays thin"],
            },
        },
        "q3": {
            "q3_unified_asset_inventory": {
                "accessible_workspace_zones": ["repo"],
                "available_cognitive_tools": ["nine_questions.q1", "nine_questions.q8"],
                "available_execution_tools": ["pytest", "requests"],
                "connected_agents": [{"agent_id": "ci-agent", "status": "verified"}],
                "activated_strategy_patches": ["query_after_write"],
            },
            "q3_resource_evaluation": {
                "resource_status": "sufficient",
                "missing_critical_assets": [],
                "bottleneck_node": None,
            },
        },
        "q4": {
            "q1_scene_model": {"primary_domain": "software_engineering"},
            "q2_role_profile": {"identity_role": "operator", "active_role": "developer", "task_role": "verifier"},
            "q3_unified_asset_inventory": {
                "available_cognitive_tools": ["nine_questions.q1"],
                "available_execution_tools": ["pytest"],
                "accessible_workspace_zones": ["repo"],
            },
            "q4_permission_profile": {"mode": "workspace-write", "is_read_only": False},
        },
        "q5": {
            "q4_capability_boundary_profile": {
                "capability_upper_limits": ["no external network without approval"],
                "actionable_space": ["edit code", "run tests"],
                "executable_strategies": ["requests based API verification"],
            },
            "q5_authorization_boundary_profile": {
                "allowed_action_space": ["edit workspace files", "run local tests"],
                "forbidden_action_space": ["hide errors", "mock API calls"],
                "contact_and_org_boundaries": {"interaction_scope": "local_workspace"},
            },
        },
        "q6": {
            "q4_capability_boundary_profile": {"actionable_space": ["edit code"]},
            "q5_authorization_boundary_profile": {"allowed_action_space": ["run tests"]},
            "q6_forbidden_zone_profile": {
                "absolute_red_lines": ["no fake tests"],
                "performance_tradeoff_bans": ["silent fallback"],
                "prohibited_strategies": ["swallow exceptions"],
                "contamination_risks": ["sandbox write into production state"],
            },
        },
        "q7": {
            "q3_resource_evaluation": {"missing_critical_assets": ["external provider"], "bottleneck_node": "live_llm"},
            "q4_capability_boundary_profile": {"capability_upper_limits": ["local only"]},
            "q5_authorization_boundary_profile": {"allowed_action_space": ["read local docs"]},
            "q6_forbidden_zone_profile": {"absolute_red_lines": ["no mock"]},
            "q7_alternative_strategy_baseline": {"fallback_plans": ["surface missing provider explicitly"]},
        },
        "q8": {
            "q8_q1_q7_snapshot": {
                "q4": {"actionable_space": ["edit code"]},
                "q5": {"explicitly_forbidden_actions": ["fake tests"]},
                "q6": {"absolute_red_lines": ["no mock"]},
                "q7": {"capability_limits": ["provider unavailable"]},
            },
            "q8_persistent_task_state": {"todo": [{"id": "task-1", "title": "finish feature 44", "status": "todo"}]},
            "cognitive_agenda": {"items": [{"id": "agenda-1", "title": "verify APIs", "status": "open"}]},
        },
        "q9": {
            "q9_q1_q8_snapshot": {
                "q1": q1_result["workspace_domain_inference"],
                "q6": {"absolute_red_lines": ["no mock"]},
                "q8": {"current_primary_objective": "finish feature 44"},
            },
            "q9_self_model": {"cognitive_load": "medium", "stability_level": "stable"},
            "q9_reasoning_budget": {"compute_remaining_ratio": 0.8, "token_remaining_ratio": 0.7, "time_remaining_ratio": 0.6},
        },
    }
    results: dict[str, dict[str, Any]] = {
        "q1": q1_result,
        "q2": {
            "role_profile": {"identity_role": "Zentex", "active_role": "implementation_verifier", "task_role": "feature_44_owner"},
            "mission_boundary": {
                "current_mission": "complete feature 44",
                "priority_duties": ["real API tests"],
                "continuity_boundaries": ["no service.py business logic"],
            },
        },
        "q3": {"resource_evaluation": contexts["q3"]["q3_resource_evaluation"]},
        "q4": {
            "q4_capability_boundary_profile": {
                "capability_upper_limits": ["workspace only"],
                "actionable_space": ["edit code", "run pytest"],
                "executable_strategies": ["read docs", "requests API checks"],
            }
        },
        "q5": {"authorization_boundary_profile": contexts["q5"]["q5_authorization_boundary_profile"]},
        "q6": {"q6_forbidden_zone_profile": contexts["q6"]["q6_forbidden_zone_profile"]},
        "q7": {
            "q7_alternative_strategy_profile": {
                "fallback_plans": ["explicitly report missing live provider"],
                "degradation_strategies": ["fail closed"],
                "collaboration_switches": ["ask for real credentials only when required"],
                "exploratory_actions": ["inspect transcript trace"],
            }
        },
        "q8": {
            "objective_profile": {
                "current_primary_objective": "complete feature 44",
                "primary_objectives": ["strict API contract"],
                "secondary_objectives": ["document update"],
                "completion_conditions": ["Q1-Q9 responses contain evidence"],
                "pause_conditions": ["real API unavailable"],
                "escalation_conditions": ["port binding blocked"],
                "priority_order": ["implement", "query", "verify"],
            },
            "task_queue": {
                "next_self_tasks": [{"task_id": "next-1", "title": "run requests API test", "status": "next"}],
                "blocked_self_tasks": [],
                "proactive_actions": [{"task_id": "proactive-1", "title": "update docs", "status": "proactive"}],
            },
        },
        "q9": {
            "q9_action_posture_profile": {
                "evaluation_profile": {"evaluation_style": "strict", "risk_level": "low", "action_rhythm_hint": "verify after every write"},
                "evolution_profile": {"allowed_directions": ["contract hardening"], "risk_threshold": "low"},
                "escalation_profile": {"confirmation_required_conditions": ["external network access"]},
            }
        },
    }
    return contexts[question_id], results[question_id]


def _seed_feature44_state(app: FastAPI) -> None:
    snapshots: dict[str, Any] = {}
    for question_id in QUESTION_DRIVER_SPECS:
        context_updates, result = _context_and_result(question_id)
        trace_id = f"{question_id}:feature44-real-trace"
        snapshots[question_id] = {
            "tool_id": f"nine_questions.{question_id}",
            "summary": f"{question_id} feature 44 real snapshot",
            "confidence": 0.91,
            "trace_id": trace_id,
            "timestamp": _now(),
            "generated_at": _now(),
            "updated_at": _now(),
            "context_updates": context_updates,
            "result": result,
        }
        app.state.transcript_store.write_entry(
            session_id=app.state.session.session_id,
            turn_id=app.state.session.last_turn_id,
            entry_type="model_provider_invoked",
            timestamp=datetime.now(timezone.utc),
            source=f"feature44.{question_id}",
            trace_id=trace_id,
            payload={
                "request_id": f"feature44-request-{question_id}",
                "decision_id": f"feature44-decision-{question_id}",
                "provider_name": "real-feature44-provider",
                "provider_plugin_id": "real-provider-plugin",
                "prompt": QUESTION_DRIVER_SPECS[question_id].question_text,
                "system_prompt": "feature 44 real driver contract",
                "context": context_updates,
                "caller_context": {
                    "source_module": f"feature44.{question_id}",
                    "invocation_phase": f"{question_id}_feature44_acceptance",
                    "question_driver_refs": [QUESTION_DRIVER_SPECS[question_id].question_text],
                },
            },
        )
        app.state.transcript_store.write_entry(
            session_id=app.state.session.session_id,
            turn_id=app.state.session.last_turn_id,
            entry_type="model_provider_completed",
            timestamp=datetime.now(timezone.utc),
            source=f"feature44.{question_id}",
            trace_id=trace_id,
            payload={
                "request_id": f"feature44-request-{question_id}",
                "decision_id": f"feature44-decision-{question_id}",
                "caller_context": {
                    "source_module": f"feature44.{question_id}",
                    "invocation_phase": f"{question_id}_feature44_acceptance",
                    "question_driver_refs": [QUESTION_DRIVER_SPECS[question_id].question_text],
                },
                "result": {"question_id": question_id, "answer": f"{question_id} live trace answer"},
                "raw_response": {"question_id": question_id, "answer": f"{question_id} live trace answer"},
                "model": "feature44-real-model",
                "elapsed_ms": 12,
                "token_usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )
    app.state.nine_question_service._state_manager.state = {
        "question_snapshots": snapshots,
        "snapshot_version": 9,
        "revision": 44,
        "dirty_questions": [],
        "last_refresh_reason": "feature44-real-seed",
        "question_driver_refs": [spec.question_text for spec in QUESTION_DRIVER_SPECS.values()],
    }


def _state_hash(app: FastAPI) -> str:
    return json.dumps(app.state.nine_question_service._state_manager.state, ensure_ascii=False, sort_keys=True)


def test_nine_question_driver_framework_q1_to_q9_real_requests_contract(acceptance_app: FastAPI) -> None:
    _seed_feature44_state(acceptance_app)

    with live_http_server(acceptance_app) as base_url:
        for question_id, spec in QUESTION_DRIVER_SPECS.items():
            response = requests.get(f"{base_url}{spec.production_api}", timeout=10)
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["question_id"] == question_id
            assert payload["title"] == spec.question_text
            assert payload["preprocessed_evidence"], f"{question_id} must expose preprocessed_evidence"
            assert payload["inference_result"], f"{question_id} must expose inference_result"
            assert payload["mounted_plugins"], f"{question_id} must expose mounted_plugins"
            assert payload["mounted_plugins"][0]["status"] == "active"
            assert payload["llm_trace_payload"]["provider_name"] == "real-feature44-provider"
            assert payload["llm_trace_payload"]["model"] == "feature44-real-model"
            assert spec.question_text in payload["llm_trace_payload"]["question_driver_refs"]
            assert payload["llm_trace_payload"]["raw_response"]["question_id"] == question_id


def test_nine_question_sandbox_api_isolated_and_queryable_by_requests(acceptance_app: FastAPI) -> None:
    _seed_feature44_state(acceptance_app)
    transcript_count_before = len(acceptance_app.state.transcript_store.entries)
    state_before = _state_hash(acceptance_app)
    q8_context, q8_result = _context_and_result("q8")

    with live_http_server(acceptance_app) as base_url:
        sandbox = requests.post(
            f"{base_url}{QUESTION_DRIVER_SPECS['q8'].sandbox_api}",
            json={"mock_context": q8_context, "mock_result": q8_result},
            timeout=10,
        )
        assert sandbox.status_code == 200, sandbox.text
        payload = sandbox.json()
        assert payload["question_id"] == "q8"
        assert payload["trace_id"].startswith("sandbox:q8:")
        assert payload["preprocessed_evidence"]["aggregated_context"]["absolute_red_line_count"] == 2
        assert payload["inference_result"]["objective_profile"]["current_primary_objective"] == "complete feature 44"
        assert payload["inference_result"]["task_queue"]["next_self_tasks"][0]["title"] == "run requests API test"
        assert payload["mounted_plugins"][0]["plugin_id"] == "nine_questions.q8.driver"
        assert QUESTION_DRIVER_SPECS["q8"].question_text in payload["llm_trace_payload"]["question_driver_refs"]

        production_after = requests.get(f"{base_url}{QUESTION_DRIVER_SPECS['q8'].production_api}", timeout=10)
        assert production_after.status_code == 200
        assert production_after.json()["trace_id"] == "q8:feature44-real-trace"

    assert _state_hash(acceptance_app) == state_before
    assert len(acceptance_app.state.transcript_store.entries) == transcript_count_before

