from __future__ import annotations

from pathlib import Path
import sys

import pytest


fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from zentex.runtime.runtime import BrainRuntime  # noqa: E402
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore  # noqa: E402
from zentex.web_console.app import create_web_console_app  # noqa: E402


def _build_client_with_q2_evidence(tmp_path: Path) -> TestClient:
    runtime = BrainRuntime(
        runtime_id="q2-production-evidence-runtime",
        transcript_store=BrainTranscriptStore(tmp_path / "production_transcript.jsonl"),
    )
    session = runtime.create_session("q2-production-evidence-session")
    state = session.current_nine_question_state
    state.current_context.update(
        {
            "workspace_domain_inference": {
                "primary_domain": "trading_engine",
                "secondary_domains": ["order_management", "risk_control"],
                "uncertainties": ["Latency jitter in quote stream"],
                "reasoning_summary": "High volatility detected in Q1 analysis.",
            },
            "identity_kernel_snapshot": {
                "meta_drives": ["strict risk boundaries", "alpha preservation"],
                "value_vetoes": ["Never use future data"],
                "non_bypassable_constraints": ["Daily drawdown < 2%", "Max position 10% per ticker"],
            },
            "manual_role_overrides": {
                "active_role_override": "Guardian of Capital",
                "applied_at": "2026-04-05T08:00:00Z",
            },
        }
    )
    state.apply_question_result(
        question_id="q2",
        tool_id="nine_questions.q2",
        summary="身份确认为受控交易代理，当前处于风险防御态。",
        confidence=0.95,
        context_updates={},
        trace_id="trace-q2-production",
        refresh_reason="unit_test",
        driver_refs=["seed:web-console", "seed:q2"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q2-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q2",
            "decision_id": "decision-q2",
            "provider_plugin_id": "gpt-4-o",
            "system_prompt": "SYSTEM_PROMPT: Determine your active role...",
            "prompt": "SYSTEM_PROMPT: Determine your active role...\n\n输入依据...",
            "context": {
                "q1_scene_model": {
                    "primary_domain": "trading_engine",
                    "secondary_domains": ["order_management", "risk_control"],
                },
                "q1_uncertainty_profile": {"risk_sources": ["Latency jitter in quote stream"]},
                "identity_kernel_snapshot": state.current_context["identity_kernel_snapshot"],
                "manual_role_overrides": state.current_context["manual_role_overrides"],
            },
            "caller_context": {
                "source_module": "q2_who_am_i_plugin",
                "invocation_phase": "nine_question_q2_who_am_i",
                "question_driver_refs": ["seed:q2"],
            },
        },
        source="test.q2.production",
        trace_id="trace-q2-production",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q2-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {
                "role_profile": {
                    "identity_role": "Clinical Strategist",
                    "active_role": "Guardian of Capital",
                    "task_role": "Risk Mitigator",
                },
                "mission_boundary": {
                    "current_mission": "De-leverage portfolio and standby for volatility reduction.",
                    "priority_duties": ["Monitor slippage", "Verify fills"],
                    "continuity_boundaries": ["Session kill-switch at 1:00 PM", "Heartbeat check every 5s"],
                },
            },
            "raw_response": {"id": "raw-q2", "role_profile": {"active_role": "Guardian of Capital"}},
            "token_usage": {"input_tokens": 140, "output_tokens": 52, "total_tokens": 192},
            "model": "gpt-4-o",
            "elapsed_ms": 500,
        },
        source="test.q2.production",
        trace_id="trace-q2-production",
    )
    app = create_web_console_app(runtime=runtime, session=session)
    return TestClient(app)


def test_latest_report_includes_q2_production_preprocessed_evidence_and_llm_trace(tmp_path: Path) -> None:
    client = _build_client_with_q2_evidence(tmp_path)

    response = client.get("/api/web/nine-questions/latest-report")

    assert response.status_code == 200
    payload = response.json()
    q2 = next(item for item in payload["questions"] if item["question_id"] == "q2")
    assert q2["preprocessed_evidence"]["q1_summary"]["primary_domain"] == "trading_engine"
    assert q2["preprocessed_evidence"]["identity_kernel"]["non_bypassable_constraints"] == [
        "Daily drawdown < 2%",
        "Max position 10% per ticker",
    ]
    assert q2["preprocessed_evidence"]["manual_intervention"]["latest_manual_role_modification"] == "Guardian of Capital"
    assert q2["inference_result"]["role_profile"]["identity_role"] == "Clinical Strategist"
    assert q2["llm_trace_payload"]["raw_response"]["id"] == "raw-q2"


def test_trace_detail_includes_q2_production_preprocessed_evidence_and_llm_trace(tmp_path: Path) -> None:
    client = _build_client_with_q2_evidence(tmp_path)

    response = client.get("/api/web/nine-questions/traces/trace-q2-production")

    assert response.status_code == 200
    payload = response.json()
    assert payload["preprocessed_evidence"]["q1_summary"]["secondary_domains"] == ["order_management", "risk_control"]
    assert payload["inference_result"]["mission_boundary"]["current_mission"].startswith("De-leverage")
    assert payload["llm_trace_payload"]["token_usage"]["total_tokens"] == 192
