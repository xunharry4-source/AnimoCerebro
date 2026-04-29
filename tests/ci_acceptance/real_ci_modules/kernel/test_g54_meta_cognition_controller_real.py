from __future__ import annotations

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _wm_frame(suffix: str) -> dict:
    return {
        "frame_id": f"g54-frame-{suffix}",
        "tick_id": f"g54-tick-{suffix}",
        "active_focus_ids": [f"active-risk-{suffix}"],
        "suspended_focus_ids": [f"suspended-a-{suffix}", f"suspended-b-{suffix}"],
        "attention_budget": {"max_active_focus": 1, "max_suspended_focus": 4},
        "attention_shift_events": [{"event_id": f"g54-shift-{suffix}", "shift_reason": "high_risk_interrupt"}],
    }


def _self_model(suffix: str) -> dict:
    return {
        "living_self_model": {
            "model_id": f"g54-model-{suffix}",
            "current_state": {
                "load_level": "high",
                "stability_level": "fragile",
                "exploration_mode": "limited",
                "reasoning_posture": "conservative",
                "evidence_posture": "evidence_first",
            },
            "current_cognitive_load": "high",
            "current_confidence_style": "cautious",
            "recent_weaknesses": [
                {
                    "pattern_id": f"g54-weakness-{suffix}",
                    "pattern_type": "premature_conclusion",
                    "frequency": 3,
                    "severity": "high",
                    "evidence_refs": [f"real-g54-weakness:{suffix}"],
                    "last_seen_at": "2026-04-29T00:00:00+00:00",
                }
            ],
            "confidence_drift_indicators": [
                {
                    "indicator_id": f"g54-drift-{suffix}",
                    "statement_confidence": 0.95,
                    "evidence_support": 0.2,
                    "drift_score": 0.75,
                    "triggered_alert": True,
                    "created_at": "2026-04-29T00:00:00+00:00",
                    "evidence_refs": [f"real-g54-drift:{suffix}"],
                }
            ],
        }
    }


def _tool_registry(suffix: str) -> dict:
    return {
        "tools": [
            {
                "tool_id": f"evidence-checker-{suffix}",
                "tool_name": "Evidence Checker",
                "capabilities": ["evidence_check"],
                "is_concurrency_safe": True,
                "mutates_working_memory": False,
            },
            {
                "tool_id": f"risk-comparator-{suffix}",
                "tool_name": "Risk Comparator",
                "capabilities": ["risk_compare"],
                "is_concurrency_safe": True,
                "mutates_working_memory": False,
            },
            {
                "tool_id": f"memory-review-{suffix}",
                "tool_name": "Working Memory Review",
                "capabilities": ["working_memory_review", "agenda_review"],
                "is_concurrency_safe": False,
                "mutates_working_memory": True,
            },
            {
                "tool_id": f"unrelated-{suffix}",
                "tool_name": "Unrelated Tool",
                "capabilities": ["unrelated"],
                "is_concurrency_safe": True,
                "mutates_working_memory": False,
            },
        ]
    }


def _agenda(suffix: str) -> list[dict]:
    return [
        {
            "item_id": f"agenda-risk-{suffix}",
            "title": "High risk item",
            "risk_level": "high",
            "goal_relevance": 0.9,
            "tags": ["agenda_review"],
        }
    ]


def test_g54_meta_cognition_service_decides_queries_and_persists_transcript_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g54-service-{suffix}")

    result = kernel_service.decide_meta_cognition(
        session_id=session_id,
        trace_id=f"g54-service-{suffix}",
        wm_frame=_wm_frame(suffix),
        self_model=_self_model(suffix),
        budget={"remaining_ratio": 0.6, "evidence_score": 0.2},
        nine_q_state={"risk_level": "high", "evidence_score": 0.2},
        agenda=_agenda(suffix),
        tool_registry=_tool_registry(suffix),
    )

    assert result["feature_code"] == "B7-54"
    assert result["operation"] == "decide"
    assert result["read_after_write"] is True
    bundle = result["queried_decision_bundle"]
    mode = bundle["reasoning_mode_decision"]
    escalation = bundle["escalation_decision"]
    plan = bundle["tool_invocation_plan"]
    assert mode["thought_mode"] == "shallow"
    assert mode["reasoning_depth"] == 1
    assert "high cognitive load" in mode["selection_reason"]
    assert escalation["decision_type"] == "clarify"
    assert "high_confidence_low_evidence" in escalation["blocking_risks"]
    selected_ids = {item["tool_id"] for item in plan["selected_tools"]}
    assert f"evidence-checker-{suffix}" in selected_ids
    assert f"risk-comparator-{suffix}" in selected_ids
    assert f"memory-review-{suffix}" in selected_ids
    assert f"unrelated-{suffix}" not in selected_ids
    assert [f"memory-review-{suffix}"] in plan["serial_groups"]
    assert any(f"evidence-checker-{suffix}" in group for group in plan["parallel_groups"])

    queried = kernel_service.query_meta_cognition_decision(session_id=session_id)
    assert queried["query_visible"] is True
    assert queried["decision_bundle"]["decision_bundle_id"] == bundle["decision_bundle_id"]

    with pytest.raises(ValueError, match="tool_registry"):
        kernel_service.decide_meta_cognition(
            session_id=session_id,
            wm_frame=_wm_frame(suffix),
            self_model=_self_model(suffix),
            budget={"remaining_ratio": 0.6},
            nine_q_state={"risk_level": "high"},
            agenda=[],
            tool_registry={"tools": []},
        )

    transcript_entries = kernel_service.get_transcript(session_id, limit=100)
    g54_payloads = [entry["payload"] for entry in transcript_entries if entry["payload"].get("feature_code") == "B7-54"]
    assert len(g54_payloads) == 1
    assert g54_payloads[0]["entry_type"] == "metacognition_decided"
    assert g54_payloads[0]["thought_mode"] == "shallow"
    assert g54_payloads[0]["decision_type"] == "clarify"
    assert set(g54_payloads[0]["selected_tool_ids"]) == selected_ids


def test_g54_phase7_consumes_phase6_tool_plan_and_fails_closed_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g54-phase7-{suffix}")
    decision = kernel_service.decide_meta_cognition(
        session_id=session_id,
        trace_id=f"g54-phase7-decide-{suffix}",
        wm_frame=_wm_frame(suffix),
        self_model=_self_model(suffix),
        budget={"remaining_ratio": 0.6, "evidence_score": 0.2},
        nine_q_state={"risk_level": "high", "evidence_score": 0.2},
        agenda=_agenda(suffix),
        tool_registry=_tool_registry(suffix),
    )

    class RealPlanConsumingPluginService:
        def __init__(self) -> None:
            self.last_context: dict | None = None

        def invoke_cognitive_tools(self, *, session_id: str, context: dict) -> dict:
            self.last_context = dict(context)
            return {
                "tool_results": [
                    {"tool_id": tool_id, "status": "planned"}
                    for tool_id in context["selected_cognitive_tool_ids"]
                ]
            }

    plugin_service = RealPlanConsumingPluginService()
    kernel_service.attach_dependencies(plugins_service=plugin_service)
    invoked = kernel_service.invoke_cognitive_tools(
        session_id,
        {"decision_bundle": decision["decision_bundle"], "trace_id": f"g54-phase7-invoke-{suffix}"},
    )
    selected_ids = [
        item["tool_id"]
        for item in decision["decision_bundle"]["tool_invocation_plan"]["selected_tools"]
    ]
    assert invoked["metacognition_plan_consumed"] is True
    assert invoked["selected_cognitive_tool_ids"] == selected_ids
    assert invoked["tool_results"] == [{"tool_id": tool_id, "status": "planned"} for tool_id in selected_ids]
    assert plugin_service.last_context is not None
    assert plugin_service.last_context["cognitive_tool_plan"]["plan_id"] == invoked["consumed_plan_id"]

    with pytest.raises(ValueError, match="decision_bundle"):
        kernel_service.invoke_cognitive_tools(session_id, {"trace_id": f"g54-phase7-missing-{suffix}"})


def test_g54_meta_cognition_api_requests_decide_query_and_fail_closed_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g54-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        decide_response = requests.post(
            f"{base_url}/api/web/runtime/meta-cognition/decide",
            json={
                "session_id": session_id,
                "trace_id": f"g54-api-{suffix}",
                "wm_frame": _wm_frame(suffix),
                "self_model": _self_model(suffix),
                "budget": {"remaining_ratio": 0.6, "evidence_score": 0.2},
                "nine_q_state": {"risk_level": "high", "evidence_score": 0.2},
                "agenda": _agenda(suffix),
                "tool_registry": _tool_registry(suffix),
            },
            timeout=20,
        )
        assert decide_response.status_code == 200, decide_response.text
        decided = decide_response.json()
        bundle = decided["queried_decision_bundle"]
        assert bundle["reasoning_mode_decision"]["thought_mode"] == "shallow"
        assert bundle["escalation_decision"]["decision_type"] == "clarify"
        assert decided["decision_bundle"]["decision_bundle_id"] == bundle["decision_bundle_id"]

        query_response = requests.get(
            f"{base_url}/api/web/runtime/meta-cognition/decision",
            params={"session_id": session_id},
            timeout=20,
        )
        assert query_response.status_code == 200, query_response.text
        queried = query_response.json()
        assert queried["decision_bundle"]["decision_bundle_id"] == bundle["decision_bundle_id"]

        fail_closed_response = requests.post(
            f"{base_url}/api/web/runtime/meta-cognition/decide",
            json={
                "session_id": session_id,
                "wm_frame": _wm_frame(suffix),
                "self_model": _self_model(suffix),
                "budget": {"remaining_ratio": 0.6},
                "nine_q_state": {"risk_level": "high"},
                "agenda": [],
                "tool_registry": {"tools": []},
            },
            timeout=20,
        )
        assert fail_closed_response.status_code == 400
        assert "tool_registry" in fail_closed_response.text
