from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

from zentex.runtime.nine_questions.state import NineQuestionState
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.session import BrainSession
from zentex.web_console.routers.nine_questions import get_latest_nine_questions_report


def test_backend_nine_questions_report_reads_runtime_state_snapshot() -> None:
    runtime = MagicMock(spec=BrainRuntime)
    session = MagicMock(spec=BrainSession)
    session.session_id = "test-session-999"
    session.last_turn_id = "5"

    state = NineQuestionState()
    state.snapshot_version = 2
    state.revision = 7
    state.last_refresh_reason = "unit_test"
    state.refreshed_at = datetime.now(timezone.utc)
    state.question_driver_refs = ["seed:web-console", "seed:q1"]
    state.apply_question_result(
        question_id="q1",
        tool_id="nine_questions.q1",
        summary="当前运行域是 web console",
        confidence=0.92,
        context_updates={"primary_domain": "web_console", "environment_description": "本地开发运行态"},
        trace_id="trace-q1",
        refresh_reason="unit_test",
        driver_refs=["seed:web-console", "seed:q1"],
    )
    state.apply_question_result(
        question_id="q6",
        tool_id="nine_questions.q6",
        summary="不能伪造运行态",
        confidence=0.97,
        context_updates={"forbidden_zone_profile": {"absolute_red_lines": ["NO_FAKE_RUNTIME_STATE"]}},
        trace_id="trace-q6",
        refresh_reason="unit_test",
        driver_refs=["seed:web-console", "seed:q6"],
    )

    session.current_nine_question_state = state
    runtime.active_session = session
    runtime.nine_question_state = state

    request = MagicMock()
    request.app.state.runtime = runtime

    response = asyncio.run(get_latest_nine_questions_report(request))

    assert response.session_id == "test-session-999"
    assert response.last_turn_id == "5"
    assert response.snapshot_version == state.snapshot_version
    assert response.revision == state.revision
    assert response.question_driver_refs == ["seed:web-console", "seed:q6"]
    assert len(response.questions) == 2

    q1 = next(q for q in response.questions if q.question_id == "q1")
    assert q1.tool_id == "nine_questions.q1"
    assert q1.summary == "当前运行域是 web console"
    assert q1.trace_id == "trace-q1"
    assert q1.context_updates["primary_domain"] == "web_console"

    q6 = next(q for q in response.questions if q.question_id == "q6")
    assert q6.summary == "不能伪造运行态"
    assert q6.context_updates["forbidden_zone_profile"]["absolute_red_lines"] == ["NO_FAKE_RUNTIME_STATE"]
