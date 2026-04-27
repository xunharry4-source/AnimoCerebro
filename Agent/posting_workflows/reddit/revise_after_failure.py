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
                "You are an expert at troubleshooting Reddit submission failures. "
                "The previous submission to r/{subreddit} failed. "
                "\nDetected Error: {error_message} "
                "\nAnalysis: {popup_analysis} "
                "\n\nRules: {rules} "
                "\n\nCurrent Title: {title} "
                "\nCurrent Content Preview: {content_preview} "
                "\n\nInstructions: "
                "1. Analyze the error and rules to determine why it failed. "
                "2. If the title is too short/long or contains prohibited words, revise it. "
                "3. If the content is too short or violates a rule, expand or modify it. "
                "4. If the error is 'Duplicate post', make the content more unique. "
                "5. Return JSON: {{\"title\": \"New Title\", \"content\": \"New Content\", \"retry_same_community\": true/false, \"explanation\": \"...\"}}. "
                "6. If the error is unfixable for this community (e.g. banned/private), set retry_same_community to false."
            ).format(
                subreddit=state.subreddit,
                error_message=state.last_submission_result.get("error_message") or "Unknown error",
                popup_analysis=state.last_popup_analysis,
                rules=state.rules,
                title=state.title,
                content_preview=(state.content or "")[:500]
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
