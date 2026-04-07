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


def _build_q8_client(tmp_path: Path) -> TestClient:
    runtime = BrainRuntime(
        runtime_id="q8-production-evidence-runtime",
        transcript_store=BrainTranscriptStore(tmp_path / "q8_production_transcript.jsonl"),
    )
    session = runtime.create_session("q8-production-evidence-session")
    state = session.current_nine_question_state
    state.current_context.update(
        {
            "q1_q7_snapshot": {
                "q1": {"primary_domain": "billing_workspace", "uncertainties": ["OCR drift"]},
                "q4": {"capability_upper_limits": ["read_csv", "generate_report"]},
                "q5": {"explicitly_forbidden_actions": ["delete_invoice"]},
                "q6": {"absolute_red_lines": ["NO_FAKE_STATE", "NO_HIDDEN_FAILURE"]},
                "q7": {"capability_limits": ["no_write_back"]},
            },
            "persistent_task_state": {
                "todo": [{"id": "todo-1", "title": "Inspect invoice batch", "priority": 80}],
                "blocked": [{"id": "blocked-1", "title": "Push production patch", "reason": "waiting for human approval"}],
            },
            "cognitive_agenda": {
                "items": [
                    {
                        "item_id": "agenda-1",
                        "title": "Review OCR drift",
                        "status": "overdue",
                        "priority": 100,
                        "next_review_condition": "needs_manual_validation",
                        "delay_risk_score": 0.92,
                    }
                ]
            },
        }
    )
    state.apply_question_result(
        question_id="q8",
        tool_id="nine_questions.q8",
        summary="当前主目标是验证发票 OCR 偏差并暂停危险写操作。",
        confidence=0.94,
        context_updates={
            "q8_objective_profile": {
                "current_primary_objective": "Stabilize OCR evidence pipeline",
                "current_phase_tasks": ["sample invoices", "verify OCR drift"],
                "priority_order": ["sample invoices", "verify OCR drift"],
            },
            "q8_task_queue": {
                "next_self_tasks": [{"id": "next-1", "title": "sample invoices"}],
                "blocked_self_tasks": [{"id": "blocked-1", "title": "push production patch", "reason": "waiting for human approval"}],
                "proactive_actions": [{"id": "pro-1", "title": "notify operator"}],
            },
        },
        trace_id="trace-q8-production",
        refresh_reason="unit_test",
        driver_refs=["seed:q8"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q8-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q8",
            "decision_id": "decision-q8",
            "provider_plugin_id": "gpt-4-o",
            "system_prompt": "SYSTEM_Q8",
            "prompt": "PROMPT_Q8",
            "context": {
                "q1_q7_snapshot": state.current_context["q1_q7_snapshot"],
                "persistent_task_state": state.current_context["persistent_task_state"],
                "cognitive_agenda": state.current_context["cognitive_agenda"],
            },
            "caller_context": {
                "source_module": "q8_what_should_i_do_now_plugin",
                "invocation_phase": "nine_question_q8_decision",
                "question_driver_refs": ["我现在应该做什么"],
            },
        },
        source="test.q8.production",
        trace_id="trace-q8-production",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q8-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {
                "objective_profile": {
                    "current_primary_objective": "Stabilize OCR evidence pipeline",
                    "current_phase_tasks": ["sample invoices", "verify OCR drift"],
                    "priority_order": ["sample invoices", "verify OCR drift"],
                },
                "task_queue": {
                    "next_self_tasks": [{"id": "next-1", "title": "sample invoices"}],
                    "blocked_self_tasks": [{"id": "blocked-1", "title": "push production patch", "reason": "waiting for human approval"}],
                    "proactive_actions": [{"id": "pro-1", "title": "notify operator"}],
                },
            },
            "raw_response": {"id": "raw-q8", "objective_profile": {"current_primary_objective": "Stabilize OCR evidence pipeline"}},
            "token_usage": {"input_tokens": 188, "output_tokens": 77, "total_tokens": 265},
            "model": "gpt-4-o",
            "elapsed_ms": 640,
        },
        source="test.q8.production",
        trace_id="trace-q8-production",
    )
    app = create_web_console_app(runtime=runtime, session=session)
    return TestClient(app)


def _build_q9_client(tmp_path: Path) -> TestClient:
    runtime = BrainRuntime(
        runtime_id="q9-production-evidence-runtime",
        transcript_store=BrainTranscriptStore(tmp_path / "q9_production_transcript.jsonl"),
    )
    session = runtime.create_session("q9-production-evidence-session")
    state = session.current_nine_question_state
    state.current_context.update(
        {
            "q1_q8_snapshot": {
                "q1": {"uncertainties": ["gateway jitter"]},
                "q5": {"explicitly_forbidden_actions": ["bypass_confirm"]},
                "q6": {"absolute_red_lines": ["NO_FAKE_TEST_RESULT"]},
                "q8": {"current_primary_objective": "stabilize pipeline"},
            },
            "living_self_model": {
                "current_cognitive_load": "high",
                "current_state": {"stability_level": "unstable"},
                "recent_weaknesses": [
                    {"pattern_id": "weak-1", "pattern_type": "overconfidence", "frequency": 2, "severity": "high"}
                ],
            },
            "confidence_drift_indicator": {"drift_score": 0.61},
            "reasoning_budget": {
                "compute_remaining_ratio": 0.25,
                "token_remaining_ratio": 0.18,
                "time_remaining_ratio": 0.42,
                "budget_pressure": "critical",
            },
        }
    )
    state.apply_question_result(
        question_id="q9",
        tool_id="nine_questions.q9",
        summary="当前行动姿态应保持零容忍、证据优先与逐步确认。",
        confidence=0.97,
        context_updates={
            "q9_action_posture_profile": {
                "evaluation_style": "evidence_first",
                "risk_tolerance": "zero_tolerance",
                "action_rhythm": "step-by-step with checkpoint",
                "confirmation_strategy": "wait for human confirmation before risky step",
                "evolution_direction": "reduce OCR drift before execution",
            }
        },
        trace_id="trace-q9-production",
        refresh_reason="unit_test",
        driver_refs=["seed:q9"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q9-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q9",
            "decision_id": "decision-q9",
            "provider_plugin_id": "gpt-4-o",
            "system_prompt": "SYSTEM_Q9",
            "prompt": "PROMPT_Q9",
            "context": {
                "q1_q8_snapshot": state.current_context["q1_q8_snapshot"],
                "living_self_model": state.current_context["living_self_model"],
                "confidence_drift_indicator": state.current_context["confidence_drift_indicator"],
                "reasoning_budget": state.current_context["reasoning_budget"],
            },
            "caller_context": {
                "source_module": "q9_how_should_i_act_plugin",
                "invocation_phase": "nine_question_q9_posture",
                "question_driver_refs": ["我应该如何行动"],
            },
        },
        source="test.q9.production",
        trace_id="trace-q9-production",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q9-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {
                "evaluation_style": "evidence_first",
                "risk_tolerance": "zero_tolerance",
                "action_rhythm": "step-by-step with checkpoint",
                "confirmation_strategy": "wait for human confirmation before risky step",
                "evolution_direction": "reduce OCR drift before execution",
            },
            "raw_response": {"id": "raw-q9", "risk_tolerance": "zero_tolerance"},
            "token_usage": {"input_tokens": 145, "output_tokens": 48, "total_tokens": 193},
            "model": "gpt-4-o",
            "elapsed_ms": 510,
        },
        source="test.q9.production",
        trace_id="trace-q9-production",
    )
    app = create_web_console_app(runtime=runtime, session=session)
    return TestClient(app)


def test_latest_report_includes_q8_production_preprocessed_evidence_and_llm_trace(tmp_path: Path) -> None:
    client = _build_q8_client(tmp_path)
    response = client.get("/api/web/nine-questions/latest-report")
    assert response.status_code == 200
    payload = response.json()
    q8 = next(item for item in payload["questions"] if item["question_id"] == "q8")
    assert q8["preprocessed_evidence"]["aggregated_context"]["absolute_red_line_count"] == 3
    assert q8["preprocessed_evidence"]["runtime_state"]["persistent_task_state"][1]["blocker_reason"] == "waiting for human approval"
    assert q8["inference_result"]["objective_profile"]["current_primary_objective"] == "Stabilize OCR evidence pipeline"
    assert q8["llm_trace_payload"]["raw_response"]["id"] == "raw-q8"


def test_trace_detail_includes_q8_production_preprocessed_evidence_and_llm_trace(tmp_path: Path) -> None:
    client = _build_q8_client(tmp_path)
    response = client.get("/api/web/nine-questions/traces/trace-q8-production")
    assert response.status_code == 200
    payload = response.json()
    assert payload["preprocessed_evidence"]["runtime_state"]["cognitive_agenda"][0]["status"] == "overdue"
    assert payload["inference_result"]["task_queue"]["blocked_self_tasks"][0]["reason"] == "waiting for human approval"
    assert payload["llm_trace_payload"]["token_usage"]["total_tokens"] == 265


def test_latest_report_includes_q9_production_preprocessed_evidence_and_llm_trace(tmp_path: Path) -> None:
    client = _build_q9_client(tmp_path)
    response = client.get("/api/web/nine-questions/latest-report")
    assert response.status_code == 200
    payload = response.json()
    q9 = next(item for item in payload["questions"] if item["question_id"] == "q9")
    assert q9["preprocessed_evidence"]["self_model"]["cognitive_load"] == "high"
    assert q9["preprocessed_evidence"]["reasoning_budget"]["token_remaining_ratio"] == 0.18
    assert q9["inference_result"]["risk_tolerance"] == "zero_tolerance"
    assert q9["llm_trace_payload"]["raw_response"]["id"] == "raw-q9"


def test_trace_detail_includes_q9_production_preprocessed_evidence_and_llm_trace(tmp_path: Path) -> None:
    client = _build_q9_client(tmp_path)
    response = client.get("/api/web/nine-questions/traces/trace-q9-production")
    assert response.status_code == 200
    payload = response.json()
    assert payload["preprocessed_evidence"]["cognitive_snapshot"]["absolute_red_line_count"] == 2
    assert payload["inference_result"]["confirmation_strategy"].startswith("wait for human confirmation")
    assert payload["llm_trace_payload"]["token_usage"]["total_tokens"] == 193
