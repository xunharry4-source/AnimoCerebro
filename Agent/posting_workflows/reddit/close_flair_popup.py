"""
Reddit node 8: close or exit Flair popup.

Purpose:
    Ensure the Flair dialog is closed before submitting the Reddit post.

Main responsibilities:
    - Wait for the dialog to close after Apply.
    - Close it explicitly if it remains open.

Not responsible for:
    - Selecting Flair.
    - Submitting the post.
    - Suppressing Apply failures.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class CloseFlairPopupNode:
    name = "reddit_close_flair_popup"

    def run(self, context: Any, state: Any) -> Any:
        recognizer = context.reddit_recognizer
        if recognizer is None:
            state.add_evidence(self.name, True, "No recognizer; close skipped")
            return state
        if not recognizer._is_flair_dialog_open():
            state.add_evidence(self.name, True, "Flair popup already closed")
            return state
        recognizer._close_flair_dialog()
        if recognizer._is_flair_dialog_open():
            raise PostingWorkflowError(
                "Flair popup remained open after close attempt",
                node=self.name,
                code="flair_close_failed",
            )
        state.add_evidence(self.name, True, "Flair popup closed")
        return state
