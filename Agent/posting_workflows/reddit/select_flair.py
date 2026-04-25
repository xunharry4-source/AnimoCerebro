"""
Reddit node 7: select Flair.

Purpose:
    Click the Flair option selected by the previous analysis node.

Main responsibilities:
    - Match selected Flair text against OCR candidates.
    - Click the candidate and apply the selection.

Not responsible for:
    - Deciding which Flair is best.
    - Opening the Flair dialog.
    - Submitting the post.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class SelectFlairNode:
    name = "reddit_select_flair"

    def run(self, context: Any, state: Any) -> Any:
        recognizer = context.reddit_recognizer
        if recognizer is None or not recognizer._is_flair_dialog_open():
            state.add_evidence(self.name, True, "No Flair dialog open; selection skipped")
            return state
        if not state.selected_flair:
            recognizer._close_flair_dialog()
            state.add_evidence(self.name, True, "No suitable Flair selected; dialog closed")
            return state

        selected = recognizer._choose_flair_candidate(
            candidates=state.flair_options,
            target_flair=state.selected_flair,
            preferred_keywords=[state.selected_flair],
        )
        if not selected:
            raise PostingWorkflowError(
                "Selected Flair was not found in OCR candidates",
                node=self.name,
                code="selected_flair_not_found",
                details={"selected_flair": state.selected_flair},
            )
        if not recognizer._click_at_coordinates(selected["center_x"], selected["center_y"]):
            raise PostingWorkflowError(
                "Could not click selected Flair",
                node=self.name,
                code="flair_click_failed",
                details={"selected_flair": state.selected_flair},
            )
        if not recognizer._click_apply_button():
            raise PostingWorkflowError(
                "Could not apply selected Flair",
                node=self.name,
                code="flair_apply_failed",
                details={"selected_flair": state.selected_flair},
            )
        state.add_evidence(self.name, True, "Flair selected", selected_flair=state.selected_flair)
        return state
