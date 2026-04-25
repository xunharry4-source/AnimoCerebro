"""
GitHub posting workflow nodes.

Purpose:
    Expose the GitHub Discussions posting workflow package.

Main responsibilities:
    - Keep GitHub-specific nodes isolated from X and Reddit workflow code.
    - Provide the importable GitHubPostingWorkflow entry point through lazy import.

Not responsible for:
    - Creating Discussions at import time.
    - Storing GitHub tokens.
    - Treating fixture tests as real GitHub posts.
"""

__all__ = ["GitHubPostingWorkflow"]


def __getattr__(name: str):
    """Lazy-load the orchestrator so node imports do not create circular imports."""
    if name == "GitHubPostingWorkflow":
        from Agent.posting_workflows.github.orchestrator import GitHubPostingWorkflow

        return GitHubPostingWorkflow
    raise AttributeError(name)
