"""
Backward compatibility layer for nine_questions router.

All implementations have been moved to nine_questions_impl package.
This module re-exports the router and constants to maintain backward compatibility.
"""

from .nine_questions_impl import router, QUESTION_TITLES, get_latest_nine_questions_report

__all__ = ["router", "QUESTION_TITLES", "get_latest_nine_questions_report"]
