"""Nine Questions router exports.

Keep imports lazy so helper modules can be imported without triggering the
full router graph.
"""

from importlib import import_module
from typing import Any

__all__ = ["router", "QUESTION_TITLES", "get_latest_nine_questions_report"]


def __getattr__(name: str) -> Any:
    if name == "router":
        module = import_module(".route_handlers", __name__)
        return module.router
    if name == "QUESTION_TITLES":
        module = import_module(".route_handlers_shared", __name__)
        return module.QUESTION_TITLES
    if name == "get_latest_nine_questions_report":
        module = import_module(".route_handlers_query", __name__)
        return module.get_latest_nine_questions_report
    raise AttributeError(name)
