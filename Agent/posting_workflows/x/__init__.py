"""
X posting workflow nodes.

Purpose:
    Group the node files that implement X posting.

Main responsibilities:
    - Keep X-specific browser and LLM workflow behavior isolated.

Not responsible for:
    - Reddit posting.
    - Running nodes at import time.
    - Storing X credentials.
"""

from Agent.posting_workflows.x.orchestrator import XPostingWorkflow

__all__ = ["XPostingWorkflow"]
