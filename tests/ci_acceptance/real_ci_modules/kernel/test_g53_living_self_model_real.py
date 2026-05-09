from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _working_memory_frame(suffix: str) -> dict:
    return {
        "frame_id": f"wm-frame-g53-{suffix}",
        "tick_id": f"g53-tick-{suffix}",
        "active_focus_ids": [f"active-risk-{suffix}"],
        "suspended_focus_ids": [f"suspended-a-{suffix}", f"suspended-b-{suffix}"],
        "attention_shift_events": [
            {
                "event_id": f"shift-{suffix}",
                "from_focus_id": f"old-{suffix}",
                "to_focus_id": f"active-risk-{suffix}",
                "shift_reason": "high_risk_interrupt",
            }
        ],
        "attention_budget": {
            "max_active_focus": 1,
            "max_suspended_focus": 4,
            "max_revisit_refs": 5,
            "overflow_policy": "suspend_noncritical",
        },
    }


def _weakness_event(suffix: str, index: int, *, severity: str = "high") -> dict:
    return {
        "event_type": "failure",
        "error_code": "premature_conclusion",
        "severity": severity,
        "evidence_refs": [f"g53-evidence-{suffix}-{index}"],
        "observed_at": f"2026-04-29T10:0{index}:00+08:00",
    }


def _turn_result(suffix: str) -> dict:
    return {
        "turn_id": f"turn-g53-{suffix}",
        "status": "failed",
        "failed": True,
        "phase_error_count": 2,
        "duration_ms": 90000,
        "risk_hit": True,
        "evidence_refs": [f"turn-evidence-{suffix}"],
    }


def test_g53_living_self_model_service_updates_queries_and_persists_transcript_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g53-service-{suffix}")
    frame = _working_memory_frame(suffix)

    weak_two = kernel_service.detect_living_self_weakness_patterns(
        session_id=session_id,
        recent_events=[_weakness_event(suffix, 1), _weakness_event(suffix, 2)],
        trace_id=f"g53-service-weakness-two-{suffix}",
    )
    assert weak_two["feature_code"] == "B2-53"
    assert weak_two["weakness_patterns"] == []
    assert weak_two["read_after_write"] is True

    weak_three = kernel_service.detect_living_self_weakness_patterns(
        session_id=session_id,
        recent_events=[_weakness_event(suffix, 1), _weakness_event(suffix, 2), _weakness_event(suffix, 3)],
        trace_id=f"g53-service-weakness-three-{suffix}",
    )
    assert len(weak_three["weakness_patterns"]) == 1
    pattern = weak_three["weakness_patterns"][0]
    assert pattern["pattern_type"] == "premature_conclusion"
    assert pattern["frequency"] == 3
    assert pattern["severity"] == "high"
    assert set(pattern["evidence_refs"]) == {
        f"g53-evidence-{suffix}-1",
        f"g53-evidence-{suffix}-2",
        f"g53-evidence-{suffix}-3",
    }

    drift = kernel_service.check_living_self_confidence_drift(
        session_id=session_id,
        statements=[
            {
                "statement_id": f"claim-{suffix}",
                "confidence": 0.92,
                "evidence_support": 0.31,
                "evidence_refs": [f"claim-evidence-{suffix}"],
            }
        ],
        evidence={f"claim-{suffix}": {"support": 0.31, "evidence_refs": [f"claim-evidence-{suffix}"]}},
        threshold=0.25,
        trace_id=f"g53-service-drift-{suffix}",
    )
    assert drift["indicator"]["triggered_alert"] is True
    assert drift["indicator"]["drift_score"] == 0.61
    assert drift["living_self_model"]["current_confidence_style"] == "cautious"
    assert any(signal["signal_type"] == "suspicion" for signal in drift["living_self_model"]["emotion_like_signals"])

    load = kernel_service.apply_living_self_load_adjustment(
        session_id=session_id,
        working_memory_frame=frame,
        trace_id=f"g53-service-load-{suffix}",
    )
    assert load["load_adjustment"]["load_level"] == "high"
    assert load["living_self_model"]["current_state"]["load_level"] == "high"
    assert load["living_self_model"]["current_state"]["reasoning_posture"] == "conservative"

    updated = kernel_service.update_living_self_model(
        session_id=session_id,
        turn_result=_turn_result(suffix),
        recent_events=[_weakness_event(suffix, 1), _weakness_event(suffix, 2), _weakness_event(suffix, 3)],
        working_memory_frame=frame,
        trace_id=f"g53-service-update-{suffix}",
    )
    model = updated["queried_living_self_model"]
    assert updated["living_self_model_status"] == "updated"
    assert updated["read_after_write"] is True
    assert model["current_state"]["load_level"] == "high"
    assert model["current_state"]["stability_level"] == "fragile"
    assert model["current_state"]["reasoning_posture"] == "conservative"
    assert model["current_risk_tolerance"] == "low"
    assert model["current_confidence_style"] == "cautious"
    assert "evidence_traceability" in model["recent_strengths"]
    assert any(item["pattern_type"] == "premature_conclusion" for item in model["recent_weaknesses"])
    assert any(signal["signal_type"] in {"alert", "suspicion"} for signal in model["emotion_like_signals"])
    assert any(source["source_type"] == "turn_result" and source["source_ref"] == f"turn-g53-{suffix}" for source in model["update_sources"])

    queried = kernel_service.query_living_self_model(session_id=session_id)
    assert queried["query_visible"] is True
    assert queried["living_self_model"]["model_id"] == model["model_id"]
    assert queried["living_self_model"]["current_state"] == model["current_state"]

    transcript_entries = kernel_service.get_transcript(session_id, limit=300)
    payloads = [entry["payload"] for entry in transcript_entries if entry["payload"].get("feature_code") == "B2-53"]
    operations = {payload["operation"] for payload in payloads}
    assert {
        "detect_weakness_pattern",
        "check_confidence_drift",
        "apply_load_adjustment",
        "update_from_turn_result",
    } <= operations
    assert all(payload["entry_type"] == "living_self_model_updated" for payload in payloads)


def test_g53_living_self_model_api_requests_update_query_and_read_after_write_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g53-api-{suffix}")
    frame = _working_memory_frame(suffix)
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        weak_two_response = requests.post(
            f"{base_url}/api/web/runtime/living-self-model/weakness-patterns",
            json={
                "session_id": session_id,
                "recent_events": [_weakness_event(suffix, 1), _weakness_event(suffix, 2)],
                "trace_id": f"g53-api-weakness-two-{suffix}",
            },
            timeout=20,
        )
        assert weak_two_response.status_code == 200, weak_two_response.text
        assert weak_two_response.json()["weakness_patterns"] == []

        no_evidence_response = requests.post(
            f"{base_url}/api/web/runtime/living-self-model/weakness-patterns",
            json={
                "session_id": session_id,
                "recent_events": [
                    {"event_type": "failure", "error_code": "no_evidence_failure", "severity": "high"},
                    {"event_type": "failure", "error_code": "no_evidence_failure", "severity": "high"},
                    {"event_type": "failure", "error_code": "no_evidence_failure", "severity": "high"},
                ],
                "trace_id": f"g53-api-no-evidence-{suffix}",
            },
            timeout=20,
        )
        assert no_evidence_response.status_code == 200, no_evidence_response.text
        no_evidence_payload = no_evidence_response.json()
        assert no_evidence_payload["weakness_patterns"] == []
        assert all(
            item["pattern_type"] != "no_evidence_failure"
            for item in no_evidence_payload["queried_living_self_model"]["recent_weaknesses"]
        )

        weakness_response = requests.post(
            f"{base_url}/api/web/runtime/living-self-model/weakness-patterns",
            json={
                "session_id": session_id,
                "recent_events": [_weakness_event(suffix, 1), _weakness_event(suffix, 2), _weakness_event(suffix, 3)],
                "trace_id": f"g53-api-weakness-three-{suffix}",
            },
            timeout=20,
        )
        assert weakness_response.status_code == 200, weakness_response.text
        weakness_payload = weakness_response.json()
        assert weakness_payload["weakness_patterns"][0]["frequency"] == 3
        assert weakness_payload["weakness_patterns"][0]["pattern_type"] == "premature_conclusion"

        low_drift_response = requests.post(
            f"{base_url}/api/web/runtime/living-self-model/confidence-drift",
            json={
                "session_id": session_id,
                "statements": [
                    {
                        "statement_id": f"api-low-drift-{suffix}",
                        "confidence": 0.55,
                        "evidence_support": 0.5,
                        "evidence_refs": [f"api-low-drift-evidence-{suffix}"],
                    }
                ],
                "evidence": {f"api-low-drift-{suffix}": {"support": 0.5, "evidence_refs": [f"api-low-drift-evidence-{suffix}"]}},
                "threshold": 0.25,
                "trace_id": f"g53-api-low-drift-{suffix}",
            },
            timeout=20,
        )
        assert low_drift_response.status_code == 200, low_drift_response.text
        low_drift_payload = low_drift_response.json()
        assert low_drift_payload["indicator"] is None
        assert not low_drift_payload["queried_living_self_model"]["confidence_drift_indicators"]

        drift_response = requests.post(
            f"{base_url}/api/web/runtime/living-self-model/confidence-drift",
            json={
                "session_id": session_id,
                "statements": [
                    {
                        "statement_id": f"api-claim-{suffix}",
                        "confidence": 0.9,
                        "evidence_support": 0.2,
                        "evidence_refs": [f"api-claim-evidence-{suffix}"],
                    }
                ],
                "evidence": {f"api-claim-{suffix}": {"support": 0.2, "evidence_refs": [f"api-claim-evidence-{suffix}"]}},
                "threshold": 0.25,
                "trace_id": f"g53-api-drift-{suffix}",
            },
            timeout=20,
        )
        assert drift_response.status_code == 200, drift_response.text
        drift_payload = drift_response.json()
        assert drift_payload["indicator"]["triggered_alert"] is True
        assert drift_payload["indicator"]["drift_score"] == 0.7
        assert drift_payload["queried_living_self_model"]["current_confidence_style"] == "cautious"

        load_response = requests.post(
            f"{base_url}/api/web/runtime/living-self-model/load-adjustment",
            json={
                "session_id": session_id,
                "working_memory_frame": frame,
                "trace_id": f"g53-api-load-{suffix}",
            },
            timeout=20,
        )
        assert load_response.status_code == 200, load_response.text
        assert load_response.json()["load_adjustment"]["load_level"] == "high"

        update_response = requests.post(
            f"{base_url}/api/web/runtime/living-self-model/update",
            json={
                "session_id": session_id,
                "turn_result": _turn_result(suffix),
                "recent_events": [_weakness_event(suffix, 1), _weakness_event(suffix, 2), _weakness_event(suffix, 3)],
                "working_memory_frame": frame,
                "trace_id": f"g53-api-update-{suffix}",
            },
            timeout=20,
        )
        assert update_response.status_code == 200, update_response.text
        updated = update_response.json()
        assert updated["read_after_write"] is True
        assert updated["queried_living_self_model"]["current_state"]["load_level"] == "high"
        assert updated["queried_living_self_model"]["current_state"]["stability_level"] == "fragile"
        assert updated["queried_living_self_model"]["current_risk_tolerance"] == "low"

        query_response = requests.get(
            f"{base_url}/api/web/runtime/living-self-model",
            params={"session_id": session_id},
            timeout=20,
        )
        assert query_response.status_code == 200, query_response.text
        queried = query_response.json()

    final_model = queried["living_self_model"]
    assert queried["query_visible"] is True
    assert final_model["model_id"] == updated["queried_living_self_model"]["model_id"]
    assert final_model["current_state"] == updated["queried_living_self_model"]["current_state"]
    assert any(item["pattern_type"] == "premature_conclusion" and item["frequency"] == 3 for item in final_model["recent_weaknesses"])
    assert any(item["triggered_alert"] is True for item in final_model["confidence_drift_indicators"])
    assert any(signal["signal_type"] in {"alert", "suspicion"} for signal in final_model["emotion_like_signals"])

    transcript_entries = kernel_service.get_transcript(session_id, limit=300)
    trace_ids = {entry["trace_id"] for entry in transcript_entries if entry["payload"].get("feature_code") == "B2-53"}
    assert f"g53-api-no-evidence-{suffix}" in trace_ids
    assert f"g53-api-low-drift-{suffix}" in trace_ids
    assert f"g53-api-weakness-three-{suffix}" in trace_ids
    assert f"g53-api-drift-{suffix}" in trace_ids
    assert f"g53-api-load-{suffix}" in trace_ids
    assert f"g53-api-update-{suffix}" in trace_ids
