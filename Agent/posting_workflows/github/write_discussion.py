"""
GitHub node 3: write Discussion title and body.

Purpose:
    Generate a repository-specific GitHub Discussion using the active LLM.

Main responsibilities:
    - Ask the active ModelProvider for a Discussion title and Markdown body.
    - Validate that title and body are non-empty and usable.
    - Store category name when provided by the model.

Not responsible for:
    - Creating the Discussion through GitHub API.
    - Verifying the final Discussion URL.
    - Using static template text when the LLM fails.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class WriteGitHubDiscussionNode:
    name = "github_write_discussion"

    def run(self, context: Any, state: Any) -> Any:
        if not state.repository or not state.topic:
            raise PostingWorkflowError(
                "GitHub repository and topic are required before writing a Discussion",
                node=self.name,
                code="github_discussion_context_missing",
                details={"repository": state.repository, "topic": state.topic},
            )
        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Write a GitHub Discussion for the target repository. Return JSON with title, body, and category_name. "
                "The body must be Markdown, specific, non-spammy, and useful to maintainers. "
                "Do not include private credentials, internal trace IDs, or unsupported claims."
            ),
            context={
                "repository": state.repository,
                "topic": state.topic,
                "category_name": state.category_name,
                "platform": "github",
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="github_discussion_content_generation",
            max_output_tokens=1800,
        )
        title = str(payload.get("title") or "").strip()
        body = str(payload.get("body") or "").strip()
        category_name = str(payload.get("category_name") or state.category_name or "").strip()
        if not title or not body:
            raise PostingWorkflowError(
                "LLM did not return GitHub Discussion title and body",
                node=self.name,
                code="github_discussion_content_missing",
                details={"payload": payload},
            )
        state.title = title
        state.content = body
        if category_name:
            state.category_name = category_name
        state.add_evidence(
            self.name,
            True,
            "GitHub Discussion content generated",
            title=title,
            category_name=state.category_name,
        )
        return state
