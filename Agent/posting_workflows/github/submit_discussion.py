"""
GitHub node 4: submit Discussion.

Purpose:
    Create a GitHub Discussion through GitHubSmartPoster and store submission evidence.

Main responsibilities:
    - Require repository, title, and body before writing to GitHub.
    - Call the GitHub GraphQL-backed poster.
    - Store the created Discussion URL and number only when API verification succeeds.

Not responsible for:
    - Generating Discussion content.
    - Recording the final ledger row.
    - Swallowing GitHub token, permission, or network failures.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.verification_gate import is_platform_post_url
from Agent.social_promotion.github_smart_poster import GitHubPostingError, GitHubSmartPoster


class SubmitGitHubDiscussionNode:
    name = "github_submit_discussion"

    def run(self, context: Any, state: Any) -> Any:
        if not state.repository or not state.title or not state.content:
            raise PostingWorkflowError(
                "Repository, title, and body are required before GitHub Discussion submission",
                node=self.name,
                code="github_discussion_submit_content_missing",
                details={
                    "repository": state.repository,
                    "has_title": bool(state.title),
                    "has_content": bool(state.content),
                },
            )
        if context.github_poster is None:
            context.github_poster = GitHubSmartPoster()
        try:
            result = context.github_poster.create_discussion_with_evidence(
                repository=state.repository,
                title=state.title,
                body=state.content,
                category_name=state.category_name,
                trace_id=context.trace_id,
            )
        except GitHubPostingError as exc:
            raise PostingWorkflowError(
                str(exc),
                node=self.name,
                code=exc.code,
                details=exc.details,
            ) from exc

        post_url = result.get("post_url")
        if not result.get("success") or not is_platform_post_url("github", post_url):
            raise PostingWorkflowError(
                "GitHub Discussion submission did not return a verified Discussion URL",
                node=self.name,
                code="github_discussion_submit_unverified",
                details={"post_url": post_url, "result": result},
            )
        state.status = "success"
        state.post_url = post_url
        state.discussion_id = result.get("discussion_id")
        state.discussion_number = result.get("discussion_number")
        category = result.get("category") or {}
        state.category_id = category.get("id")
        state.category_name = category.get("name") or state.category_name
        state.attempts += 1
        state.last_submission_result = result
        state.add_evidence(self.name, True, "GitHub Discussion created and API-verified", result=result)
        return state
