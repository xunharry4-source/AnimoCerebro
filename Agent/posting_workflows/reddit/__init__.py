"""
Reddit posting workflow nodes.

Purpose:
    Group the LangGraph node files that implement Reddit posting.

Main responsibilities:
    - Expose the RedditPostingWorkflow entry point.

Not responsible for:
    - X posting.
    - Running browser automation at import time.
    - Managing Reddit credentials.
"""

from Agent.posting_workflows.reddit.orchestrator import RedditPostingWorkflow

__all__ = ["RedditPostingWorkflow"]
