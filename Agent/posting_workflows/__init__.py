"""
Node-based social posting workflows.

Purpose:
    Expose X, Reddit, and GitHub posting orchestrators built from small, auditable nodes.

Main responsibilities:
    - Provide importable workflow entry points through lazy imports.
    - Keep platform workflow code separated by package.
    - Avoid importing every platform stack when a shared helper is loaded.

Not responsible for:
    - Starting workflows at import time.
    - Storing account credentials.
    - Claiming real posting success without platform evidence.
"""

__all__ = ["XPostingWorkflow", "RedditPostingWorkflow", "GitHubPostingWorkflow"]


def __getattr__(name: str):
    """Lazy-load platform orchestrators to avoid cross-platform circular imports."""
    if name == "XPostingWorkflow":
        from Agent.posting_workflows.x.orchestrator import XPostingWorkflow

        return XPostingWorkflow
    if name == "RedditPostingWorkflow":
        from Agent.posting_workflows.reddit.orchestrator import RedditPostingWorkflow

        return RedditPostingWorkflow
    if name == "GitHubPostingWorkflow":
        from Agent.posting_workflows.github.orchestrator import GitHubPostingWorkflow

        return GitHubPostingWorkflow
    raise AttributeError(name)
