#!/usr/bin/env python3
"""
Reddit popup LLM interpreter tests.

Purpose:
    Verify the Reddit popup interpreter's JSON contract handling without
    touching Reddit, a browser, or a live model provider.

Main responsibilities:
    - Cover normal provider output.
    - Cover provider failure as fail-closed behavior.
    - Cover malformed provider output as an edge case.

Not responsible for:
    - Proving live LLM availability.
    - Proving real Reddit popup wording.
    - Exercising Playwright, OCR, or account state.
"""

from types import SimpleNamespace

import pytest

from Agent.reddit_popup_llm_interpreter import (
    RedditPopupLLMError,
    RedditPopupLLMInterpreter,
)


class FakeLLMService:
    """Isolated test fake; not used by production runtime."""

    def __init__(self, output=None, exc=None):
        self.output = output
        self.exc = exc
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return SimpleNamespace(output=self.output)


def _valid_output(**overrides):
    payload = {
        "status": "error",
        "language": "en",
        "translated_message_zh": "此社区要求帖子必须添加 Flair。",
        "summary_zh": "缺少社区 Flair，发帖被阻止。",
        "category": "flair_required",
        "should_retry": True,
        "needs_flair": True,
        "recommended_action": "select_flair",
        "confidence": 0.94,
        "reason": "The popup says post flair is required.",
    }
    payload.update(overrides)
    return payload


def test_interpret_popup_normal_flair_required():
    service = FakeLLMService(output=_valid_output())
    interpreter = RedditPopupLLMInterpreter(llm_service=service)

    result = interpreter.interpret(
        message="Your post must contain post flair.",
        subreddit="AnimoCerebro",
        source="dom",
        trace_id="trace-normal",
    )

    assert result["status"] == "error"
    assert result["category"] == "flair_required"
    assert result["needs_flair"] is True
    assert result["recommended_action"] == "select_flair"
    assert result["translated_message_zh"] == "此社区要求帖子必须添加 Flair。"
    assert service.calls[0]["caller_context"].trace_id == "trace-normal"
    assert service.calls[0]["context"]["popup_message"] == "Your post must contain post flair."


def test_interpret_popup_abnormal_provider_failure_is_fail_closed():
    service = FakeLLMService(exc=RuntimeError("provider offline"))
    interpreter = RedditPopupLLMInterpreter(llm_service=service)

    with pytest.raises(RedditPopupLLMError, match="provider invocation failed"):
        interpreter.interpret(message="Try again later.", trace_id="trace-failure")


def test_interpret_popup_edge_invalid_status_is_rejected():
    service = FakeLLMService(output=_valid_output(status="maybe"))
    interpreter = RedditPopupLLMInterpreter(llm_service=service)

    with pytest.raises(RedditPopupLLMError, match="invalid status"):
        interpreter.interpret(message="Ambiguous community popup.", trace_id="trace-edge")
