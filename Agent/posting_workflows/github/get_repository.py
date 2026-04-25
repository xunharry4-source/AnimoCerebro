"""
GitHub node 1: resolve target repository.

Purpose:
    Normalize the GitHub target repository before content generation or posting.

Main responsibilities:
    - Accept a repository URL or owner/repo value.
    - Default to xunharry4-source/AnimoCerebro when none is provided.
    - Store normalized owner/repo in GitHubPostingState.

Not responsible for:
    - Checking token permissions.
    - Creating a GitHub Discussion.
    - Claiming the repository is writable.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.social_promotion.github_smart_poster import DEFAULT_GITHUB_REPOSITORY, GitHubPostingError, GitHubSmartPoster


class GetGitHubRepositoryNode:
    name = "github_get_repository"

    def __init__(self, repository: str | None = None) -> None:
        self.repository = repository or DEFAULT_GITHUB_REPOSITORY

    def run(self, context: Any, state: Any) -> Any:
        try:
            repository = GitHubSmartPoster(token="placeholder-token").normalize_repository(
                state.repository or self.repository
            )
        except GitHubPostingError as exc:
            raise PostingWorkflowError(
                str(exc),
                node=self.name,
                code=exc.code,
                details=exc.details,
            ) from exc
        state.repository = repository
        state.add_evidence(self.name, True, "GitHub repository resolved", repository=repository)
        return state
