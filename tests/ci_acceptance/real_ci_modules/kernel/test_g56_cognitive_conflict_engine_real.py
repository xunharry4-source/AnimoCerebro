from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.foundation.contracts import TurnRequest
from zentex.kernel.flow_domain.think_loop import ThinkLoop
from zentex.kernel.state_domain import CognitiveTemporalEngine, SelfModelEngine, WorkingMemoryController
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _working_memory(suffix: str) -> dict:
    return {
        "frame_id": f"g56-frame-{suffix}",
        "active_items": [
            {
                "item_id": f"evidence-support-{suffix}",
                "claim_key": f"deploy-safe-{suffix}",
                "polarity": "supports",
                "source_ref": f"wm-support-{suffix}",
            },
            {
                "item_id": f"evidence-oppose-{suffix}",
                "claim_key": f"deploy-safe-{suffix}",
                "polarity": "opposes",
                "source_ref": f"wm-oppose-{suffix}",
            },
        ],
    }


def _goals(suffix: str) -> list[dict]:
    return [
        {"goal_id": f"ship-now-{suffix}", "title": "Ship immediately", "conflicts_with": [f"block-release-{suffix}"]},
        {"goal_id": f"block-release-{suffix}", "title": "Block release until evidence improves"},
    ]


def _memory_recalls(suffix: str) -> list[dict]:
    return [
        {
            "memory_id": f"memory-positive-{suffix}",
            "memory_key": f"incident-state-{suffix}",
            "conclusion": "true",
        },
        {
            "memory_id": f"memory-negative-{suffix}",
            "memory_key": f"incident-state-{suffix}",
            "conclusion": "false",
        },
    ]


def _self_model(suffix: str) -> dict:
    return {
        "living_self_model": {
            "confidence_drift_indicators": [
                {
                    "indicator_id": f"drift-{suffix}",
                    "triggered_alert": True,
                    "statement_confidence": 0.93,
                    "evidence_support": 0.2,
                    "drift_score": 0.73,
                    "evidence_refs": [f"self-model-evidence-{suffix}"],
                }
            ]
        }
    }


def _budget(suffix: str) -> dict:
    return {
        "budget_id": f"budget-{suffix}",
        "remaining_ratio": 0.1,
        "planned_steps": 4,
    }


def _nine_q_state(suffix: str) -> dict:
    return {"boundary_violations": [f"q9-boundary-{suffix}"]}


def _agenda(suffix: str) -> list[dict]:
    return [{"item_id": f"agenda-{idx}-{suffix}"} for idx in range(4)]


def _assert_conflict_payload(payload: dict, suffix: str) -> None:
    assert payload["feature_code"] == "B5-56"
    assert payload["operation"] == "detect_cognitive_conflicts"
    assert payload["read_after_write"] is True
    assert payload["deterministic"] is True
    assert payload["llm_required"] is False
    reports = payload["conflict_reports"]
    conflict_types = {report["conflict_type"] for report in reports}
    assert {
        "goal_conflict",
        "evidence_conflict",
        "memory_conflict",
        "confidence_conflict",
        "budget_conflict",
        "boundary_conflict",
    } <= conflict_types
    by_type = {report["conflict_type"]: report for report in reports}
    assert by_type["boundary_conflict"]["severity"] == "critical"
    assert by_type["boundary_conflict"]["reconciliation_plan"]["blocking"] is True
    assert by_type["evidence_conflict"]["severity"] == "medium"
    assert f"wm-support-{suffix}" in by_type["evidence_conflict"]["source_refs"]
    assert f"wm-oppose-{suffix}" in by_type["evidence_conflict"]["source_refs"]
    assert by_type["confidence_conflict"]["suggested_resolution"] == "downgrade_confidence"
    assert f"self-model-evidence-{suffix}" in by_type["confidence_conflict"]["source_refs"]
    triggers = payload["self_correction_triggers"]
    assert any(trigger["must_pause_current_path"] is True for trigger in triggers)
    assert all(trigger["recommended_phase"] == "metacognition" for trigger in triggers)
    assert len(payload["reconciliation_plans"]) == len(reports)
    assert len(payload["queried_conflict_reports"]) >= len(reports)


def test_g56_cognitive_conflict_service_detects_queries_phase4_and_persists_transcript_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g56-service-{suffix}")

    detected = kernel_service.detect_cognitive_conflicts(
        session_id=session_id,
        working_memory=_working_memory(suffix),
        goals=_goals(suffix),
        nine_q_state=_nine_q_state(suffix),
        memory_recalls=_memory_recalls(suffix),
        budget=_budget(suffix),
        self_model=_self_model(suffix),
        agenda=_agenda(suffix),
        trace_id=f"g56-service-detect-{suffix}",
    )
    _assert_conflict_payload(detected, suffix)

    queried = kernel_service.query_cognitive_conflicts(session_id=session_id)
    assert queried["query_visible"] is True
    assert queried["brain_scope"] == session_id
    assert {report["conflict_type"] for report in queried["conflict_reports"]} >= {
        "goal_conflict",
        "boundary_conflict",
    }
    assert any(trigger["must_pause_current_path"] is True for trigger in queried["self_correction_triggers"])

    phase4 = kernel_service.detect_conflicts(
        session_id,
        {
            "trace_id": f"g56-phase4-{suffix}",
            "working_memory": _working_memory(f"phase4-{suffix}"),
            "goals": _goals(f"phase4-{suffix}"),
            "nine_q_state": _nine_q_state(f"phase4-{suffix}"),
            "memory_recalls": _memory_recalls(f"phase4-{suffix}"),
            "budget": _budget(f"phase4-{suffix}"),
            "self_model": _self_model(f"phase4-{suffix}"),
            "agenda": _agenda(f"phase4-{suffix}"),
        },
    )
    assert phase4["feature_code"] == "B5-56"
    assert len(phase4["conflict_reports"]) == 6

    transcript_entries = kernel_service.get_transcript(session_id, limit=300)
    payloads = [entry["payload"] for entry in transcript_entries if entry["payload"].get("feature_code") == "B5-56"]
    assert len(payloads) >= 2
    assert all(payload["entry_type"] == "conflict_snapshot_written" for payload in payloads)
    assert any(payload["conflict_report_count"] == 6 for payload in payloads)
    assert any("boundary_conflict" in payload["conflict_types"] for payload in payloads)


def test_g56_cognitive_conflict_api_requests_detect_query_and_empty_state_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g56-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        empty_query = requests.get(
            f"{base_url}/api/web/runtime/cognitive-conflicts",
            params={"session_id": session_id},
            timeout=20,
        )
        assert empty_query.status_code == 200, empty_query.text
        assert empty_query.json()["conflict_reports"] == []

        detect_response = requests.post(
            f"{base_url}/api/web/runtime/cognitive-conflicts/detect",
            json={
                "session_id": session_id,
                "working_memory": _working_memory(suffix),
                "goals": _goals(suffix),
                "nine_q_state": _nine_q_state(suffix),
                "memory_recalls": _memory_recalls(suffix),
                "budget": _budget(suffix),
                "self_model": _self_model(suffix),
                "agenda": _agenda(suffix),
                "trace_id": f"g56-api-detect-{suffix}",
            },
            timeout=20,
        )
        assert detect_response.status_code == 200, detect_response.text
        detected = detect_response.json()
        _assert_conflict_payload(detected, suffix)

        query_response = requests.get(
            f"{base_url}/api/web/runtime/cognitive-conflicts",
            params={"session_id": session_id},
            timeout=20,
        )
        assert query_response.status_code == 200, query_response.text
        queried = query_response.json()
        assert len(queried["conflict_reports"]) >= 6
        assert {report["conflict_type"] for report in queried["conflict_reports"]} >= {
            "goal_conflict",
            "evidence_conflict",
            "memory_conflict",
            "confidence_conflict",
            "budget_conflict",
            "boundary_conflict",
        }

        invalid_response = requests.post(
            f"{base_url}/api/web/runtime/cognitive-conflicts/detect",
            json={
                "session_id": session_id,
                "working_memory": {},
            },
            timeout=20,
        )
        assert invalid_response.status_code == 422


class _G56B7Bridge:
    def __init__(self, suffix: str) -> None:
        self.suffix = suffix
        self.metacognition_context: dict | None = None

    def observe_environment(self, session_id: str, turn_id: str) -> dict:
        return {
            "observed": True,
            "attention_candidates": [
                {
                    "focus_id": f"normal-focus-{self.suffix}",
                    "source_ref": f"normal-source-{self.suffix}",
                    "title": "normal work",
                    "summary": "normal work before cognitive risk interruption",
                }
            ],
        }

    def evaluate_drive(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"drive_checked": True}

    def evaluate_cognition(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"frame_checked": True}

    def detect_conflicts(self, session_id: str, context: dict) -> dict:
        return {
            "feature_code": "B5-56",
            "operation": "detect_cognitive_conflicts",
            "conflict_reports": [
                {
                    "report_id": f"report-critical-{self.suffix}",
                    "conflict_id": f"report-critical-{self.suffix}",
                    "conflict_type": "boundary_conflict",
                    "severity": "critical",
                    "summary": "critical boundary conflict",
                    "source_refs": [f"boundary-{self.suffix}"],
                    "suggested_resolution": "request_help",
                }
            ],
            "self_correction_triggers": [
                {
                    "trigger_id": f"trigger-critical-{self.suffix}",
                    "report_id": f"report-critical-{self.suffix}",
                    "conflict_id": f"report-critical-{self.suffix}",
                    "trigger_reason": "boundary_conflict:request_help",
                    "recommended_phase": "metacognition",
                    "must_pause_current_path": True,
                }
            ],
        }

    def run_simulation(self, session_id: str, context: dict) -> dict:
        return {"simulation": {"branches": ["pause current path"]}}

    def run_metacognition(self, session_id: str, context: dict) -> dict:
        self.metacognition_context = dict(context)
        return {
            "metacognition_received_self_correction": bool(context.get("self_correction_triggers")),
            "metacognition_received_interrupts": bool(context.get("cognitive_risk_interrupts_applied")),
            "recommended_mode": "clarify",
        }

    def invoke_cognitive_tools(self, session_id: str, context: dict) -> dict:
        return {"tool_results": []}

    def synthesize_decision(self, session_id: str, context: dict) -> dict:
        return {"response": "paused for self correction"}

    def consolidate_memory(self, session_id: str, turn_id: str, context: dict) -> dict:
        return {"memory_consolidated": True}


def test_g56_think_loop_phase4_self_correction_trigger_reaches_b7_and_interrupts_working_memory_real() -> None:
    suffix = unique_suffix()
    bridge = _G56B7Bridge(suffix)
    loop = ThinkLoop(bridge=bridge)
    working_memory = WorkingMemoryController(max_slots=3)
    request = TurnRequest(
        session_id=f"g56-b7-session-{suffix}",
        turn_id=f"g56-b7-turn-{suffix}",
        user_input="trigger critical cognitive conflict",
        context={},
    )

    results = loop.run(
        request=request,
        working_memory=working_memory,
        self_model=SelfModelEngine(session_id=request.session_id),
        temporal=CognitiveTemporalEngine(session_id=request.session_id),
    )

    by_phase = {result.phase_name: result for result in results}
    cognitive_risks = by_phase["cognitive_risks"].output
    assert cognitive_risks["self_correction_triggers"][0]["must_pause_current_path"] is True
    assert cognitive_risks["cognitive_risk_interrupts_applied"]
    interrupt_frame = cognitive_risks["working_memory_frame"]
    expected_focus_id = f"risk-focus-trigger-critical-{suffix}"
    assert expected_focus_id in interrupt_frame["active_focus_ids"]
    assert bridge.metacognition_context is not None
    assert bridge.metacognition_context["self_correction_triggers"][0]["recommended_phase"] == "metacognition"
    assert bridge.metacognition_context["cognitive_risk_interrupts_applied"][0]["accepted_focus_ids"] == [expected_focus_id]
    assert bridge.metacognition_context["cognitive_risk_interrupts_applied"][0]["attention_shift_events"][-1]["to_focus_id"] == expected_focus_id
    assert by_phase["metacognition"].output["metacognition_received_self_correction"] is True
    assert by_phase["metacognition"].output["metacognition_received_interrupts"] is True
