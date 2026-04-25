#!/usr/bin/env python3
"""
Reddit popup LLM interpreter.

Purpose:
    Translate and classify Reddit post-submission popup content with the active
    Agent local ModelProvider so community-specific wording is handled semantically.

Main responsibilities:
    - Call the configured Agent local LLM service for popup interpretation.
    - Validate the provider JSON contract strictly.
    - Fail closed when the LLM is missing, unavailable, or returns invalid data.

Not responsible for:
    - Capturing DOM, screenshots, or OCR text.
    - Choosing Flair coordinates or clicking Reddit controls.
    - Masking Reddit restrictions with synthetic fallback states.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from Agent.local_llm_client import AgentLocalLLMService, AgentModelCallerContext
from Agent.reddit_popup_llm_prompt import build_reddit_popup_interpretation_prompt


class RedditPopupLLMError(RuntimeError):
    """Raised when Reddit popup interpretation cannot be trusted."""

    def __init__(self, message: str, *, trace_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.trace_id = trace_id


class RedditPopupLLMInterpreter:
    """LLM-backed interpreter for Reddit popup/toast submission messages."""

    STATUSES = {"success", "error", "unknown"}
    CATEGORIES = {
        "posted",
        "flair_required",
        "title_issue",
        "content_issue",
        "duplicate",
        "rate_limit",
        "permission_denied",
        "moderation_queue",
        "removed_or_blocked",
        "captcha_or_auth",
        "network_or_reddit_error",
        "community_rule",
        "unknown",
    }
    ACTIONS = {
        "none",
        "select_flair",
        "edit_title",
        "edit_content",
        "edit_post",
        "wait_then_retry",
        "manual_review",
        "login_or_verify",
        "stop",
    }

    def __init__(
        self,
        llm_service: Optional[Any] = None,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._llm_service = llm_service
        self._provider_key = provider_key
        self._model = model

    def interpret(
        self,
        *,
        message: str,
        subreddit: Optional[str] = None,
        source: str = "unknown",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Translate and classify a Reddit popup message with the active LLM."""
        normalized_message = str(message or "").strip()
        if not normalized_message:
            raise RedditPopupLLMError("reddit_popup_llm: empty popup message")

        effective_trace_id = trace_id or f"reddit-popup-{uuid4().hex[:12]}"
        service = self._resolve_llm_service(effective_trace_id)
        caller_context = AgentModelCallerContext(
            source_module="Agent.reddit_popup_llm_interpreter",
            invocation_phase="reddit_popup_interpretation",
            decision_id=effective_trace_id,
            trace_id=effective_trace_id,
        )

        try:
            response = service.generate_json(
                prompt=build_reddit_popup_interpretation_prompt(),
                context={
                    "popup_message": normalized_message,
                    "subreddit": subreddit,
                    "source": source,
                },
                caller_context=caller_context,
                source_module="Agent.reddit_popup_llm_interpreter",
                invocation_phase="reddit_popup_interpretation",
                decision_id=effective_trace_id,
                provider_key=self._provider_key,
                model=self._model,
                temperature=0.0,
                max_output_tokens=700,
                metadata={
                    "trace_id": effective_trace_id,
                    "workflow": "reddit_post_submission_popup",
                },
            )
        except Exception as exc:
            raise RedditPopupLLMError(
                f"reddit_popup_llm: provider invocation failed: {exc.__class__.__name__}: {exc}",
                trace_id=effective_trace_id,
            ) from exc

        payload = getattr(response, "output", response)
        interpretation = self._validate_payload(payload, effective_trace_id)
        interpretation.update(
            {
                "trace_id": effective_trace_id,
                "message": normalized_message,
                "subreddit": subreddit,
                "source": source,
            }
        )
        return interpretation

    def _resolve_llm_service(self, trace_id: str) -> Any:
        """Load the default LLM service lazily so imports remain testable."""
        if self._llm_service is not None:
            return self._llm_service

        self._llm_service = AgentLocalLLMService()
        return self._llm_service

    def _validate_payload(self, payload: Any, trace_id: str) -> Dict[str, Any]:
        """Validate LLM output instead of accepting partial or malformed JSON."""
        if not isinstance(payload, dict):
            raise RedditPopupLLMError(
                "reddit_popup_llm: provider output is not a JSON object",
                trace_id=trace_id,
            )

        status = self._required_choice(payload, "status", self.STATUSES, trace_id)
        category = self._required_choice(payload, "category", self.CATEGORIES, trace_id)
        recommended_action = self._required_choice(
            payload,
            "recommended_action",
            self.ACTIONS,
            trace_id,
        )
        should_retry = self._required_bool(payload, "should_retry", trace_id)
        needs_flair = self._required_bool(payload, "needs_flair", trace_id)
        confidence = self._required_confidence(payload, trace_id)

        return {
            "status": status,
            "language": self._required_text(payload, "language", trace_id),
            "translated_message_zh": self._required_text(
                payload,
                "translated_message_zh",
                trace_id,
            ),
            "summary_zh": self._required_text(payload, "summary_zh", trace_id),
            "category": category,
            "should_retry": should_retry,
            "needs_flair": needs_flair,
            "recommended_action": recommended_action,
            "confidence": confidence,
            "reason": self._required_text(payload, "reason", trace_id),
        }

    def _required_choice(
        self,
        payload: Dict[str, Any],
        key: str,
        allowed: set[str],
        trace_id: str,
    ) -> str:
        value = str(payload.get(key) or "").strip().lower()
        if value not in allowed:
            raise RedditPopupLLMError(
                f"reddit_popup_llm: invalid {key}: {value or '<empty>'}",
                trace_id=trace_id,
            )
        return value

    def _required_bool(self, payload: Dict[str, Any], key: str, trace_id: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            raise RedditPopupLLMError(
                f"reddit_popup_llm: {key} must be boolean",
                trace_id=trace_id,
            )
        return value

    def _required_confidence(self, payload: Dict[str, Any], trace_id: str) -> float:
        try:
            confidence = float(payload.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise RedditPopupLLMError(
                "reddit_popup_llm: confidence must be numeric",
                trace_id=trace_id,
            ) from exc
        if confidence < 0 or confidence > 1:
            raise RedditPopupLLMError(
                "reddit_popup_llm: confidence must be between 0 and 1",
                trace_id=trace_id,
            )
        return confidence

    def _required_text(self, payload: Dict[str, Any], key: str, trace_id: str) -> str:
        value = str(payload.get(key) or "").strip()
        if not value:
            raise RedditPopupLLMError(
                f"reddit_popup_llm: missing {key}",
                trace_id=trace_id,
            )
        return value
