from __future__ import annotations

import pytest
import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from tests.ci_acceptance.real_ci_modules.service_helpers import unique_suffix
from zentex.kernel.flow_domain.think_loop import ThinkLoop
from zentex.web_console.di_container import WebConsoleContainer
from zentex.web_console.router import api_router


CURRENT_TIME = "2026-04-29T12:00:00+00:00"


def _agenda_items(suffix: str) -> list[dict]:
    return [
        {
            "item_id": f"review-now-{suffix}",
            "title": "High risk stale hypothesis",
            "summary": "Needs immediate temporal review",
            "status": "open",
            "created_at": "2026-04-26T12:00:00+00:00",
            "last_reviewed_at": "2026-04-27T12:00:00+00:00",
            "review_count": 1,
            "review_interval_seconds": 3600,
            "grace_period_seconds": 0,
            "expire_after_seconds": 604800,
            "cooldown_seconds": 3600,
            "last_resurfaced_at": "2026-04-29T06:00:00+00:00",
            "impact_score": 0.9,
            "uncertainty_score": 0.8,
            "resurface_threshold": 0.35,
            "risk_level": "high",
        },
        {
            "item_id": f"cooldown-{suffix}",
            "title": "Recently surfaced reminder",
            "summary": "Should be suppressed by cooldown",
            "status": "open",
            "created_at": "2026-04-26T12:00:00+00:00",
            "last_reviewed_at": "2026-04-27T12:00:00+00:00",
            "review_interval_seconds": 3600,
            "grace_period_seconds": 0,
            "expire_after_seconds": 604800,
            "cooldown_seconds": 7200,
            "last_resurfaced_at": "2026-04-29T11:30:00+00:00",
            "impact_score": 0.9,
            "uncertainty_score": 0.8,
            "resurface_threshold": 0.35,
            "risk_level": "high",
        },
        {
            "item_id": f"expired-{suffix}",
            "title": "Expired waiting condition",
            "summary": "Must be marked expired, not deleted",
            "status": "open",
            "created_at": "2026-04-20T12:00:00+00:00",
            "last_reviewed_at": "2026-04-20T12:00:00+00:00",
            "review_interval_seconds": 3600,
            "expire_after_seconds": 86400,
            "impact_score": 1.0,
            "uncertainty_score": 1.0,
            "risk_level": "critical",
        },
        {
            "item_id": f"watching-{suffix}",
            "title": "Fresh watching item",
            "summary": "Not yet due",
            "status": "watching",
            "created_at": "2026-04-29T11:50:00+00:00",
            "last_reviewed_at": "2026-04-29T11:50:00+00:00",
            "review_interval_seconds": 86400,
            "expire_after_seconds": 604800,
            "impact_score": 0.2,
            "uncertainty_score": 0.2,
            "risk_level": "low",
        },
    ]


def _index_by(items: list[dict], key: str = "item_id") -> dict[str, dict]:
    return {item[key]: item for item in items}


def test_g55_temporal_agenda_service_ticks_queries_and_persists_transcript_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g55-service-{suffix}")

    tick = kernel_service.tick_temporal_agenda(
        session_id=session_id,
        current_time=CURRENT_TIME,
        agenda_items=_agenda_items(suffix),
        brain_scope=f"brain-scope-{suffix}",
        trace_id=f"g55-service-tick-{suffix}",
    )
    assert tick["feature_code"] == "B3-55"
    assert tick["operation"] == "tick_agenda"
    assert tick["read_after_write"] is True
    state = tick["queried_temporal_agenda_state"]
    assert state["snapshot_version"] == 1
    assert state["brain_scope"] == f"brain-scope-{suffix}"
    assert f"review-now-{suffix}" in state["review_now_item_ids"]
    assert f"cooldown-{suffix}" not in state["review_now_item_ids"]
    assert f"cooldown-{suffix}" in state["suppressed_item_ids"]
    assert f"expired-{suffix}" in state["expired_item_ids"]
    assert f"expired-{suffix}" not in state["open_item_ids"]
    assert f"watching-{suffix}" in state["watching_item_ids"]

    ages = _index_by(state["agenda_ages"])
    assert ages[f"review-now-{suffix}"]["overdue"] is True
    assert ages[f"review-now-{suffix}"]["expired"] is False
    assert ages[f"expired-{suffix}"]["expired"] is True
    assert ages[f"watching-{suffix}"]["overdue"] is False

    risks = _index_by(state["deferred_risk_scores"])
    assert risks[f"review-now-{suffix}"]["combined_score"] == 0.72
    assert risks[f"cooldown-{suffix}"]["combined_score"] == 0.72
    cooldowns = _index_by(state["reminder_cooldowns"])
    assert cooldowns[f"cooldown-{suffix}"]["suppressed_count"] == 1
    candidates = state["resurfaced_attention_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["focus_id"] == f"temporal-review:review-now-{suffix}"
    assert candidates[0]["source_ref"] == f"review-now-{suffix}"
    assert candidates[0]["deferred_risk_score"]["combined_score"] == 0.72
    cognitive_agenda = state["cognitive_agenda"]
    assert cognitive_agenda["review_now_item_ids"] == [f"review-now-{suffix}"]
    assert cognitive_agenda["expired_item_ids"] == [f"expired-{suffix}"]
    ordered_ids = [item["item_id"] for item in cognitive_agenda["ordered_items"]]
    assert ordered_ids[0] == f"review-now-{suffix}"
    assert set(ordered_ids) == {
        f"review-now-{suffix}",
        f"cooldown-{suffix}",
        f"expired-{suffix}",
        f"watching-{suffix}",
    }
    assert ordered_ids.index(f"expired-{suffix}") > ordered_ids.index(f"watching-{suffix}")
    assert ordered_ids.index(f"cooldown-{suffix}") > ordered_ids.index(f"watching-{suffix}")
    assert cognitive_agenda["ordered_items"][0]["deferred_risk_score"]["combined_score"] == 0.72
    working_state = ThinkLoop._working_state_phase(
        kernel_service._get_state(session_id).working_memory,
        {
            "turn_id": f"g55-phase3-{suffix}",
            "temporal_agenda_state": state,
            "attention_budget": {
                "max_active_focus": 2,
                "max_suspended_focus": 3,
                "max_revisit_refs": 5,
            },
        },
    )
    assert working_state["temporal_agenda_candidates_consumed"] is True
    assert working_state["consumed_temporal_review_item_ids"] == [f"review-now-{suffix}"]
    assert f"temporal-review:review-now-{suffix}" in working_state["working_memory_frame"]["active_focus_ids"]

    second_tick = kernel_service.tick_temporal_agenda(
        session_id=session_id,
        current_time=CURRENT_TIME,
        agenda_items=_agenda_items(suffix),
        brain_scope=f"brain-scope-{suffix}",
        trace_id=f"g55-service-second-{suffix}",
    )
    assert second_tick["queried_temporal_agenda_state"]["snapshot_version"] == 2
    second_cooldowns = _index_by(second_tick["queried_temporal_agenda_state"]["reminder_cooldowns"])
    assert second_cooldowns[f"cooldown-{suffix}"]["suppressed_count"] == 2

    queried = kernel_service.query_temporal_agenda_state(session_id=session_id)
    assert queried["query_visible"] is True
    assert queried["temporal_agenda_state"]["state_id"] == second_tick["queried_temporal_agenda_state"]["state_id"]
    assert queried["temporal_agenda_state"]["snapshot_version"] == 2

    with pytest.raises(ValueError, match="item_id"):
        kernel_service.tick_temporal_agenda(
            session_id=session_id,
            current_time=CURRENT_TIME,
            agenda_items=[{"title": "missing id"}],
            trace_id=f"g55-service-invalid-{suffix}",
        )

    transcript_entries = kernel_service.get_transcript(session_id, limit=300)
    payloads = [entry["payload"] for entry in transcript_entries if entry["payload"].get("feature_code") == "B3-55"]
    assert [payload["snapshot_version"] for payload in payloads[:2]] == [2, 1]
    assert all(payload["entry_type"] == "temporal_agenda_updated" for payload in payloads)
    assert payloads[0]["suppressed_item_ids"] == [f"cooldown-{suffix}"]


def test_g55_temporal_agenda_api_requests_tick_query_and_fail_closed_real(
    real_ci_runtime,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ZENTEX_ENABLE_TRANSCRIPTS", "1")
    suffix = unique_suffix()
    kernel_service = real_ci_runtime.facade._get_kernel_service()
    session_id = kernel_service.create_session(user_id=f"g55-api-{suffix}")
    WebConsoleContainer.initialize(kernel_service=real_ci_runtime.facade)
    app = FastAPI()
    app.include_router(api_router)

    with live_http_server(app) as base_url:
        tick_response = requests.post(
            f"{base_url}/api/web/runtime/temporal-agenda/tick",
            json={
                "session_id": session_id,
                "current_time": CURRENT_TIME,
                "agenda_items": _agenda_items(suffix),
                "brain_scope": f"api-brain-scope-{suffix}",
                "trace_id": f"g55-api-tick-{suffix}",
            },
            timeout=20,
        )
        assert tick_response.status_code == 200, tick_response.text
        tick = tick_response.json()
        state = tick["queried_temporal_agenda_state"]
        assert tick["read_after_write"] is True
        assert state["brain_scope"] == f"api-brain-scope-{suffix}"
        assert state["review_now_item_ids"] == [f"review-now-{suffix}"]
        assert state["suppressed_item_ids"] == [f"cooldown-{suffix}"]
        assert state["expired_item_ids"] == [f"expired-{suffix}"]

        query_response = requests.get(
            f"{base_url}/api/web/runtime/temporal-agenda/state",
            params={"session_id": session_id},
            timeout=20,
        )
        assert query_response.status_code == 200, query_response.text
        queried = query_response.json()
        assert queried["temporal_agenda_state"]["state_id"] == state["state_id"]
        assert queried["temporal_agenda_state"]["review_now_item_ids"] == [f"review-now-{suffix}"]

        invalid_response = requests.post(
            f"{base_url}/api/web/runtime/temporal-agenda/tick",
            json={
                "session_id": session_id,
                "current_time": CURRENT_TIME,
                "agenda_items": [{"title": "missing id"}],
            },
            timeout=20,
        )
        assert invalid_response.status_code == 400
        assert "item_id" in invalid_response.text
