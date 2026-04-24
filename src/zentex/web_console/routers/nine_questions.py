from __future__ import annotations

"""Compatibility exports for nine-question web-console APIs."""

from zentex.web_console.routers.nine_questions_impl import (
    QUESTION_TITLES,
    get_latest_nine_questions_report,
)

__all__ = ["QUESTION_TITLES", "get_latest_nine_questions_report"]
