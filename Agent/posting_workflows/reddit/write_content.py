"""
Reddit node 4: write title and content.

Purpose:
    Generate a subreddit-specific Reddit post title and body with the active LLM.

Main responsibilities:
    - Use community rules as prompt context.
    - Store generated title/content in workflow state.

Not responsible for:
    - Submitting the post.
    - Choosing Flair.
    - Reusing static promotional templates when LLM fails.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class WriteRedditContentNode:
    name = "reddit_write_content"

    def run(self, context: Any, state: Any) -> Any:
        if not state.subreddit or not state.rules:
            raise PostingWorkflowError(
                "Subreddit and rules are required before content generation",
                node=self.name,
                code="missing_content_context",
            )
        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Write a Reddit post for the selected community. Return JSON with title and content. "
                "The post must be useful, technical, and comply with the supplied rules. "
                "Do not use obvious spam or direct sales language."
            ),
            context={
                "subreddit": state.subreddit,
                "rules": state.rules,
                "previous_popup_analysis": state.last_popup_analysis,
                "attempt": state.attempts + 1,
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="reddit_content_generation",
            max_output_tokens=1800,
        )
        title = str(payload.get("title") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not title or not content:
            raise PostingWorkflowError(
                "LLM did not return Reddit title and content",
                node=self.name,
                code="missing_reddit_content",
                details={"payload": payload},
            )
        state.title = title
        state.content = content
        state.add_evidence(self.name, True, "Reddit content generated", subreddit=state.subreddit, title=title)
        return state
