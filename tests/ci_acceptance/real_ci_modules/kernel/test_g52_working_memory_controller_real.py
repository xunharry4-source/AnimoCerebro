from __future__ import annotations

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


def _candidate(
    suffix: str,
    focus_id: str,
    *,
    source_ref: str,
    title: str,
    priority: float,
    urgency: float,
    uncertainty: float,
    risk_interrupt: bool = False,
) -> dict:
    return {
        "focus_id": f"{focus_id}-{suffix}",
        "focus_type": "risk" if risk_interrupt else "agenda",
        "title": title,
        "summary": f"{title} summary {suffix}",
        "source_ref": f"{source_ref}:{suffix}",
        "priority": priority,
        "urgency": urgency,
        "uncertainty": uncertainty,
        "interruptible": True,
        "resume_hint": f"resume {title} after blocker clears",
        "risk_interrupt": risk_interrupt,
    }


def _assert_frame_budget(frame: dict, *, max_active: int, max_suspended: int) -> None:
    assert frame["attention_budget"]["max_active_focus"] == max_active
    assert frame["attention_budget"]["max_suspended_focus"] == max_suspended
    assert len(frame["active_focus_ids"]) <= max_active
    assert len(frame["suspended_focus_ids"]) <= max_suspended


def test_g52_working_memory_service_updates_interrupts_resumes_and_persists_transcript_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g52-service-{suffix}")
    tick_id = f"g52-tick-{suffix}"

    first = kernel_service.update_working_memory_frame(
        session_id=session_id,
        tick_id=tick_id,
        trace_id=f"g52-service-update-{suffix}",
        attention_budget={
            "max_active_focus": 2,
            "max_suspended_focus": 4,
            "max_revisit_refs": 3,
            "overflow_policy": "suspend_noncritical",
        },
        new_candidates=[
            _candidate(suffix, "low", source_ref="agenda-low", title="Low priority branch", priority=1, urgency=1, uncertainty=1),
            _candidate(suffix, "high", source_ref="agenda-high", title="High priority branch", priority=4, urgency=2, uncertainty=1),
            _candidate(suffix, "mid", source_ref="agenda-mid", title="Medium branch", priority=2, urgency=2, uncertainty=1),
        ],
    )

    assert first["feature_code"] == "B1-52"
    assert first["working_memory_status"] == "updated"
    assert first["operation"] == "update_frame"
    assert first["read_after_write"] is True
    frame = first["queried_frame"]
    _assert_frame_budget(frame, max_active=2, max_suspended=4)
    assert frame["active_focus_ids"] == [f"high-{suffix}", f"mid-{suffix}"]
    assert frame["suspended_focus_ids"] == [f"low-{suffix}"]
    assert {item["focus_id"] for item in frame["active_items"]} == {f"high-{suffix}", f"mid-{suffix}"}
    assert frame["context_summary"].startswith("active=2:")

    marked = kernel_service.mark_working_memory_considered(
        session_id=session_id,
        tick_id=tick_id,
        ref_id=f"duplicate-ref:{suffix}",
        trace_id=f"g52-service-considered-{suffix}",
    )
    assert f"duplicate-ref:{suffix}" in marked["queried_frame"]["recently_considered_refs"]

    duplicate = kernel_service.update_working_memory_frame(
        session_id=session_id,
        tick_id=f"{tick_id}-duplicate",
        trace_id=f"g52-service-duplicate-{suffix}",
        new_candidates=[
            _candidate(
                suffix,
                "duplicate",
                source_ref="duplicate-ref",
                title="Duplicate branch",
                priority=9,
                urgency=9,
                uncertainty=1,
            )
        ],
    )
    assert duplicate["rejected_candidates"] == [
        {
            "focus_id": f"duplicate-{suffix}",
            "source_ref": f"duplicate-ref:{suffix}",
            "reason": "recently_considered_ref",
        }
    ]
    assert f"duplicate-{suffix}" not in duplicate["queried_frame"]["active_focus_ids"]

    interrupted = kernel_service.interrupt_working_memory_focus(
        session_id=session_id,
        tick_id=f"{tick_id}-interrupt",
        trace_id=f"g52-service-interrupt-{suffix}",
        high_risk_item=_candidate(
            suffix,
            "risk",
            source_ref="risk-critical",
            title="Critical risk interrupt",
            priority=10,
            urgency=10,
            uncertainty=1,
            risk_interrupt=True,
        ),
    )
    interrupt_frame = interrupted["queried_frame"]
    assert f"risk-{suffix}" in interrupt_frame["active_focus_ids"]
    assert f"mid-{suffix}" in interrupt_frame["suspended_focus_ids"]
    interrupt_event = next(event for event in interrupted["attention_shift_events"] if event["shift_reason"] == "high_risk_interrupt")
    assert interrupt_event["from_focus_id"] == f"mid-{suffix}"
    assert interrupt_event["to_focus_id"] == f"risk-{suffix}"
    suspended_mid = next(item for item in interrupt_frame["suspended_items"] if item["focus_id"] == f"mid-{suffix}")
    assert suspended_mid["resume_hint"]

    resumed = kernel_service.resume_working_memory_focus(
        session_id=session_id,
        tick_id=f"{tick_id}-resume",
        focus_id=f"mid-{suffix}",
        trace_id=f"g52-service-resume-{suffix}",
    )
    resume_frame = resumed["queried_frame"]
    assert f"mid-{suffix}" in resume_frame["active_focus_ids"]
    assert any(event["shift_reason"] == "resume_condition_met" for event in resumed["attention_shift_events"])

    queried = kernel_service.query_working_memory_frame(session_id=session_id)
    assert queried["query_visible"] is True
    assert queried["frame"]["frame_id"] == resume_frame["frame_id"]
    assert queried["frame"]["active_focus_ids"] == resume_frame["active_focus_ids"]

    transcript_entries = kernel_service.get_transcript(session_id, limit=300)
    g52_payloads = [entry["payload"] for entry in transcript_entries if entry["payload"].get("feature_code") == "B1-52"]
    assert any(payload.get("entry_type") == "working_memory_updated" for payload in g52_payloads)
    shift_reasons = {
        payload.get("shift_reason")
        for payload in g52_payloads
        if payload.get("entry_type") == "attention_shift_event"
    }
    assert {"candidate_activated", "high_risk_interrupt", "resume_condition_met"} <= shift_reasons


def test_g52_working_memory_api_requests_update_query_interrupt_resume_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g52-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        update_response = requests.post(
            f"{base_url}/api/web/runtime/working-memory/frame",
            json={
                "session_id": session_id,
                "tick_id": f"g52-api-tick-{suffix}",
                "trace_id": f"g52-api-update-{suffix}",
                "attention_budget": {
                    "max_active_focus": 1,
                    "max_suspended_focus": 3,
                    "max_revisit_refs": 2,
                    "overflow_policy": "suspend_noncritical",
                },
                "new_candidates": [
                    _candidate(suffix, "api-active", source_ref="api-active", title="API active", priority=5, urgency=2, uncertainty=1),
                    _candidate(suffix, "api-suspend", source_ref="api-suspend", title="API suspend", priority=1, urgency=1, uncertainty=1),
                ],
            },
            timeout=20,
        )
        assert update_response.status_code == 200, update_response.text
        updated = update_response.json()

        query_response = requests.get(
            f"{base_url}/api/web/runtime/working-memory/frame",
            params={"session_id": session_id},
            timeout=20,
        )

        considered_response = requests.post(
            f"{base_url}/api/web/runtime/working-memory/considered",
            json={
                "session_id": session_id,
                "tick_id": f"g52-api-considered-{suffix}",
                "ref_id": f"api-duplicate:{suffix}",
                "trace_id": f"g52-api-considered-{suffix}",
            },
            timeout=20,
        )
        assert considered_response.status_code == 200, considered_response.text

        duplicate_response = requests.post(
            f"{base_url}/api/web/runtime/working-memory/frame",
            json={
                "session_id": session_id,
                "tick_id": f"g52-api-duplicate-{suffix}",
                "new_candidates": [
                    _candidate(
                        suffix,
                        "api-duplicate",
                        source_ref="api-duplicate",
                        title="API duplicate",
                        priority=9,
                        urgency=9,
                        uncertainty=1,
                    )
                ],
            },
            timeout=20,
        )

        interrupt_response = requests.post(
            f"{base_url}/api/web/runtime/working-memory/interrupt",
            json={
                "session_id": session_id,
                "tick_id": f"g52-api-interrupt-{suffix}",
                "trace_id": f"g52-api-interrupt-{suffix}",
                "high_risk_item": _candidate(
                    suffix,
                    "api-risk",
                    source_ref="api-risk",
                    title="API risk",
                    priority=10,
                    urgency=10,
                    uncertainty=1,
                    risk_interrupt=True,
                ),
            },
            timeout=20,
        )
        assert interrupt_response.status_code == 200, interrupt_response.text
        interrupted = interrupt_response.json()
        suspended_focus_id = interrupted["attention_shift_events"][0]["from_focus_id"]

        resume_response = requests.post(
            f"{base_url}/api/web/runtime/working-memory/resume",
            json={
                "session_id": session_id,
                "tick_id": f"g52-api-resume-{suffix}",
                "focus_id": suspended_focus_id,
                "trace_id": f"g52-api-resume-{suffix}",
            },
            timeout=20,
        )
        final_query_response = requests.get(
            f"{base_url}/api/web/runtime/working-memory/frame",
            params={"session_id": session_id},
            timeout=20,
        )

    assert updated["read_after_write"] is True
    assert updated["queried_frame"]["active_focus_ids"] == [f"api-active-{suffix}"]
    assert updated["queried_frame"]["suspended_focus_ids"] == [f"api-suspend-{suffix}"]
    assert query_response.status_code == 200, query_response.text
    queried = query_response.json()
    assert queried["frame"]["frame_id"] == updated["queried_frame"]["frame_id"]
    assert queried["frame"]["attention_budget"]["max_active_focus"] == 1

    assert duplicate_response.status_code == 200, duplicate_response.text
    duplicate = duplicate_response.json()
    assert duplicate["rejected_candidates"][0]["reason"] == "recently_considered_ref"
    assert f"api-duplicate-{suffix}" not in duplicate["queried_frame"]["active_focus_ids"]

    assert f"api-risk-{suffix}" in interrupted["queried_frame"]["active_focus_ids"]
    assert interrupted["attention_shift_events"][0]["shift_reason"] == "high_risk_interrupt"

    assert resume_response.status_code == 200, resume_response.text
    resumed = resume_response.json()
    assert resumed["attention_shift_events"][0]["shift_reason"] == "resume_condition_met"
    assert suspended_focus_id in resumed["queried_frame"]["active_focus_ids"]

    assert final_query_response.status_code == 200, final_query_response.text
    final_frame = final_query_response.json()["frame"]
    assert final_frame["frame_id"] == resumed["queried_frame"]["frame_id"]
    assert final_frame["active_focus_ids"] == resumed["queried_frame"]["active_focus_ids"]
    assert len(final_frame["suspended_focus_ids"]) <= 3

    transcript_entries = kernel_service.get_transcript(session_id, limit=300)
    trace_ids = {entry["trace_id"] for entry in transcript_entries if entry["payload"].get("feature_code") == "B1-52"}
    assert f"g52-api-update-{suffix}" in trace_ids
    assert f"g52-api-interrupt-{suffix}" in trace_ids
    assert f"g52-api-resume-{suffix}" in trace_ids
