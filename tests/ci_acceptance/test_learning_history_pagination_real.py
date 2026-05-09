from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from fastapi import FastAPI

from tests.ci_acceptance.real_ci_modules.kernel.http_server import live_http_server
from zentex.learning.service import LEARNING_EVENT_TYPE, LEARNING_SESSION_ID, LearningService
from zentex.web_console.routers import learning as learning_router


def _learning_api_app(learning_service: LearningService) -> FastAPI:
    app = FastAPI()
    app.state.learning_service = learning_service
    app.include_router(learning_router.router, prefix="/api/web")
    return app


def test_learning_history_api_is_database_backed_strict_paginated_and_descending() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_root = Path(tmpdir)
        service = LearningService(storage_root=storage_root)
        base_time = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
        expected_trace_ids: list[str] = []
        for index in range(5):
            trace_id = f"strict-learning-trace-{index}"
            expected_trace_ids.append(trace_id)
            service.store.write_entry(
                session_id=LEARNING_SESSION_ID,
                turn_id=f"turn-{index}",
                entry_type=LEARNING_EVENT_TYPE,
                payload={
                    "kind": "strict_page_test",
                    "direction": "pagination",
                    "summary": f"strict learning row {index}",
                    "question_driver_refs": [f"q{index + 1}"],
                },
                source="tests.ci_acceptance.learning_pagination",
                trace_id=trace_id,
                timestamp=base_time + timedelta(minutes=index),
            )

        with sqlite3.connect(service.store.db_path) as conn:
            db_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM learning_events
                WHERE session_id = ? AND entry_type = ?
                """,
                (LEARNING_SESSION_ID, LEARNING_EVENT_TYPE),
            ).fetchone()[0]
        assert db_count == 5

        with live_http_server(_learning_api_app(service)) as base_url:
            first_response = requests.get(
                f"{base_url}/api/web/learning/history?page=1&page_size=2",
                timeout=10,
            )
            assert first_response.status_code == 200, first_response.text
            first_page = first_response.json()

            second_response = requests.get(
                f"{base_url}/api/web/learning/history?page=2&page_size=2",
                timeout=10,
            )
            assert second_response.status_code == 200, second_response.text
            second_page = second_response.json()

            third_response = requests.get(
                f"{base_url}/api/web/learning/history?page=3&page_size=2",
                timeout=10,
            )
            assert third_response.status_code == 200, third_response.text
            third_page = third_response.json()

        assert first_page["page"] == 1
        assert first_page["page_size"] == 2
        assert first_page["total_items"] == 5
        assert first_page["total_pages"] == 3
        assert [row["trace_id"] for row in first_page["rows"]] == [
            expected_trace_ids[4],
            expected_trace_ids[3],
        ]
        assert [row["summary"] for row in first_page["rows"]] == [
            "strict learning row 4",
            "strict learning row 3",
        ]
        assert [row["question_driver_refs"] for row in first_page["rows"]] == [["q5"], ["q4"]]

        assert second_page["page"] == 2
        assert second_page["page_size"] == 2
        assert second_page["total_items"] == 5
        assert second_page["total_pages"] == 3
        assert [row["trace_id"] for row in second_page["rows"]] == [
            expected_trace_ids[2],
            expected_trace_ids[1],
        ]

        assert third_page["page"] == 3
        assert third_page["page_size"] == 2
        assert third_page["total_items"] == 5
        assert third_page["total_pages"] == 3
        assert [row["trace_id"] for row in third_page["rows"]] == [expected_trace_ids[0]]

        all_returned_ids = {
            row["trace_id"]
            for page in (first_page, second_page, third_page)
            for row in page["rows"]
        }
        assert all_returned_ids == set(expected_trace_ids)
