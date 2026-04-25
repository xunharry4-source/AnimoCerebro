"""
Reddit retry node: close popup and revise content.

Purpose:
    Prepare the next Reddit loop iteration after a failed submission.

Main responsibilities:
    - Close visible submission popups.
    - Ask the active LLM to revise title/content based on popup analysis.
    - Keep retry state explicit.

Not responsible for:
    - Submitting revised content.
    - Inventing corrections without LLM output.
    - Retrying after max retry count.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class ReviseAfterFailureNode:
    name = "reddit_revise_after_failure"

    def run(self, context: Any, state: Any) -> Any:
        if state.attempts >= context.max_retries:
            state.status = "failed"
            state.add_evidence(self.name, False, "Max Reddit retries reached", attempts=state.attempts)
            return state
        recognizer = context.reddit_recognizer
        if recognizer is not None:
            recognizer._close_submission_popup()

        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Revise the Reddit title/content after a failed submission. "
                "Return JSON with title, content, retry_same_community boolean. "
                "Do not invent success; only produce revised content."
            ),
            context={
                "subreddit": state.subreddit,
                "rules": state.rules,
                "title": state.title,
                "content": state.content,
                "popup_analysis": state.last_popup_analysis,
                "submission_result": state.last_submission_result,
                "attempts": state.attempts,
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="reddit_failure_revision",
            max_output_tokens=1800,
        )
        title = str(payload.get("title") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not title or not content:
            raise PostingWorkflowError(
                "LLM did not return revised Reddit title/content",
                node=self.name,
                code="missing_revised_content",
                details={"payload": payload},
            )
        state.title = title
        state.content = content
        state.status = "retrying_same_community" if payload.get("retry_same_community", True) else "retrying_new_community"
        state.add_evidence(
            self.name,
            True,
            "Reddit content revised for retry",
            retry_same_community=state.status == "retrying_same_community",
            title=title,
        )
        return state
