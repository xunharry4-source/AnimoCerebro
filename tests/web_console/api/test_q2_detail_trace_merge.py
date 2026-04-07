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


def test_q2_detail_merges_state_context_when_trace_context_misses_q1_summary(tmp_path: Path) -> None:
    runtime = BrainRuntime(
        runtime_id="q2-detail-merge-runtime",
        transcript_store=BrainTranscriptStore(tmp_path / "q2-detail-merge.jsonl"),
    )
    session = runtime.create_session("q2-detail-merge-session")
    state = session.current_nine_question_state
    state.current_context.update(
        {
            "workspace_domain_inference": {
                "primary_domain": "audit_workspace",
                "secondary_domains": ["frontend", "runtime"],
                "uncertainties": ["mixed historical traces"],
                "reasoning_summary": "Q1 confirms this is a live audit-oriented engineering workspace.",
            },
            "q1_scene_model": {
                "primary_domain": "audit_workspace",
                "secondary_domains": ["frontend", "runtime"],
                "suggested_first_step": "inspect trace continuity",
            },
            "q1_uncertainty_profile": {
                "risk_sources": ["mixed historical traces"],
                "risk_summary": "Q1 context is partially stale and must be merged with live state.",
                "uncertainty_intensity": 0.42,
            },
            "identity_kernel_snapshot": {
                "meta_motivation": "Maintain an auditable, truthful runtime control plane.",
                "values_prohibition": "No fabricated runtime state, no hidden failures, no unsafe escalation.",
                "non_bypassable_constraints": ["NO_FAKE_RUNTIME_STATE", "NO_SKIP_AUDIT"],
            },
        }
    )
    state.apply_question_result(
        question_id="q2",
        tool_id="nine_questions.q2",
        summary="Q2 completed",
        confidence=0.91,
        context_updates={
            "q2_role_profile": {
                "identity_role": "Runtime Auditor",
                "active_role": "Trace Examiner",
                "task_role": "Evidence Verifier",
            }
        },
        trace_id="trace-q2-merge",
        refresh_reason="unit_test",
        driver_refs=["seed:q2"],
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q2-merge",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        payload={
            "request_id": "req-q2-merge",
            "decision_id": "decision-q2-merge",
            "provider_plugin_id": "model-provider-openai-compat",
            "prompt": "q2 prompt",
            "context": {
                "identity_kernel_snapshot": {
                    "meta_motivation": {"internal": "machine-shape"},
                    "values_prohibition": ["forbid hidden writes"],
                    "non_bypassable_constraints": ["NO_FAKE_RUNTIME_STATE"],
                },
                "manual_role_overrides": {},
            },
            "caller_context": {
                "source_module": "q2_who_am_i_plugin",
                "invocation_phase": "nine_question_q2_who_am_i",
                "question_driver_refs": ["seed:q2"],
            },
        },
        source="test.q2.detail.merge",
        trace_id="trace-q2-merge",
    )
    runtime.transcript_store.write_entry(
        session_id=session.session_id,
        turn_id="turn-q2-merge",
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        payload={
            "result": {
                "role_profile": {
                    "identity_role": "Runtime Auditor",
                    "active_role": "Trace Examiner",
                    "task_role": "Evidence Verifier",
                },
                "mission_boundary": {
                    "current_mission": "verify q1-to-q2 continuity",
                    "priority_duties": ["merge stale and live context"],
                    "continuity_boundaries": ["NO_FAKE_RUNTIME_STATE"],
                },
            },
            "model": "fake-model",
            "elapsed_ms": 12,
        },
        source="test.q2.detail.merge",
        trace_id="trace-q2-merge",
    )

    client = TestClient(create_web_console_app(runtime=runtime, session=session))

    response = client.get("/api/web/nine-questions/q2")

    assert response.status_code == 200
    payload = response.json()
    evidence = payload["preprocessed_evidence"]
    assert evidence["q1_summary"]["primary_domain"] == "audit_workspace"
    assert evidence["q1_summary"]["secondary_domains"] == ["frontend", "runtime"]
    assert evidence["q1_summary"]["uncertainties"] == ["mixed historical traces"]
    assert evidence["identity_kernel"]["meta_motivation"] == "Maintain an auditable, truthful runtime control plane."
