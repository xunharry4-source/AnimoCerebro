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


def _build_client_with_q1_evidence(tmp_path: Path) -> TestClient:
    runtime = BrainRuntime(
        runtime_id="q1-production-evidence-runtime",
        transcript_store=BrainTranscriptStore(tmp_path / "production_transcript.jsonl"),
    )
    session = runtime.create_session("q1-production-evidence-session")
    state = session.current_nine_question_state
    state.current_context.update(
        {
            "workspace_structure_analysis": {
                "directory_hierarchy_summary": "src/, logs/, data/",
                "top_level_dirs": ["src", "logs", "data"],
                "file_total_count": 42,
                "suffix_distribution": {".py": 10, ".md": 3, ".log": 2},
                "high_frequency_filename_keywords": {"invoice": 2, "api": 4},
                "candidate_groups": ["python_code", "logs"],
                "obvious_risk_files": ["data/invoices.csv"],
            },
            "workspace_content_samples": {
                "sampled_file_summaries": [
                    {
                        "path": "logs/app.log",
                        "summary": "长日志样本",
                        "snippet": "ERROR sandbox validation failed on line 1",
                        "header": "ts,level,message",
                    }
                ],
                "log_anomaly_snippets": ["ERROR sandbox validation failed on line 1"],
            },
            "environment_event": {"kind": "production_run", "summary": "runtime snapshot"},
            "physical_host_state": {"memory_pressure": "high", "network_health": "degraded"},
        }
    )
    state.apply_question_result(
        question_id="q1",
        tool_id="nine_questions.q1",
        summary="正式详情页必须显示完整证据。",
        confidence=0.96,
        context_updates={
            "workspace_domain_inference": {"primary_domain": "sandbox_console"},
            "q1_llm_upgrade": {
                "planning_status": "candidate_planned",
                "profile": {
                    "program_id": "nine_questions.q1.where_am_i",
                    "target_component": "workspace_domain_inference",
                    "baseline_version": "1.0.0",
                    "target_metric": "q1_domain_accuracy",
                    "objective_summary": "Improve Q1 environment inference quality.",
                    "dataset_refs": ["tests/plugins/test_q1_where_am_i_plugin.py"],
                    "validation_commands": ["pytest tests/plugins/test_q1_where_am_i_plugin.py -q"],
                },
                "candidate_version": "1.1.0-candidate",
                "release_gate": ["Validation commands must pass before candidate promotion."],
            },
        },
        trace_id="trace-q1-production",
        refresh_reason="unit_test",
        driver_refs=["seed:web-console", "seed:q1"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q1-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q1",
            "decision_id": "decision-q1",
            "provider_plugin_id": "provider-tools-default",
            "system_prompt": "SYSTEM_PROMPT: infer environment",
            "prompt": "PROMPT_Q1_PRODUCTION",
            "context": state.current_context,
            "caller_context": {
                "source_module": "NineQuestionQ1WhereAmI",
                "invocation_phase": "phase_7_orchestrate_cognitive_tools",
                "question_driver_refs": ["seed:q1"],
            },
        },
        source="test.q1.production",
        trace_id="trace-q1-production",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q1-production",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {
                "primary_domain": "sandbox_console",
                "secondary_domains": ["ops_console", "billing_workspace"],
                "confidence": 0.96,
                "reasoning_summary": "目录结构与日志样本显示这是一个独立测试环境。",
                "uncertainties": ["仍缺少更多 data/ 抽样"],
                "suggested_first_step": "inspect sandbox output",
            },
            "raw_response": {"id": "raw-q1", "choices": [{"message": {"content": "{\"primary_domain\":\"sandbox_console\"}"}}]},
            "token_usage": {"input_tokens": 101, "output_tokens": 27, "total_tokens": 128},
            "model": "gemini-3-flash(auto)",
            "elapsed_ms": 1280,
        },
        source="test.q1.production",
        trace_id="trace-q1-production",
    )

    app = create_web_console_app(runtime=runtime, session=session)
    return TestClient(app)


def test_latest_report_includes_q1_production_preprocessed_evidence(tmp_path: Path) -> None:
    client = _build_client_with_q1_evidence(tmp_path)

    response = client.get("/api/web/nine-questions/latest-report")

    assert response.status_code == 200
    payload = response.json()
    q1 = next(item for item in payload["questions"] if item["question_id"] == "q1")
    assert q1["preprocessed_evidence"]["physical_and_environment"]["memory_pressure"] == "high"
    assert q1["preprocessed_evidence"]["workspace_structure"]["suffix_distribution"][".py"] == 10
    assert q1["preprocessed_evidence"]["workspace_content_sampling"]["long_text_evidence"][0]["text"] == "ts,level,message"
    assert q1["inference_result"]["primary_domain"] == "sandbox_console"
    assert q1["inference_result"]["secondary_domains"] == ["ops_console", "billing_workspace"]
    assert q1["q1_llm_upgrade"]["planning_status"] == "candidate_planned"
    assert q1["q1_llm_upgrade"]["candidate_version"] == "1.1.0-candidate"
    assert q1["llm_trace_payload"]["system_prompt"] == "SYSTEM_PROMPT: infer environment"
    assert q1["llm_trace_payload"]["token_usage"]["total_tokens"] == 128


def test_trace_detail_includes_q1_production_preprocessed_evidence(tmp_path: Path) -> None:
    client = _build_client_with_q1_evidence(tmp_path)

    response = client.get("/api/web/nine-questions/traces/trace-q1-production")

    assert response.status_code == 200
    payload = response.json()
    assert payload["preprocessed_evidence"]["workspace_structure"]["file_total_count"] == 42
    assert payload["preprocessed_evidence"]["workspace_content_sampling"]["long_text_evidence"][0]["label"] == "logs/app.log · 表头"
    assert payload["inference_result"]["suggested_first_step"] == "inspect sandbox output"
    assert payload["q1_llm_upgrade"]["profile"]["target_metric"] == "q1_domain_accuracy"
    assert payload["llm_trace_payload"]["raw_response"]["id"] == "raw-q1"


def test_trace_detail_includes_q1_llm_upgrade_payload(tmp_path: Path) -> None:
    client = _build_client_with_q1_evidence(tmp_path)

    response = client.get("/api/web/nine-questions/traces/trace-q1-production")

    assert response.status_code == 200
    payload = response.json()
    assert payload["q1_llm_upgrade"]["planning_status"] == "candidate_planned"
    assert payload["q1_llm_upgrade"]["profile"]["program_id"] == "nine_questions.q1.where_am_i"
