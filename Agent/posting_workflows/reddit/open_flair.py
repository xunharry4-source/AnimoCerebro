"""
Reddit node 5: open Flair dialog.

Purpose:
    Open the Reddit Flair dialog for the selected post.

Main responsibilities:
    - Initialize RedditVisualRecognizer when needed.
    - Open the Flair dialog if the page exposes one.

Not responsible for:
    - Selecting a Flair.
    - Analyzing Flair semantics.
    - Treating absent optional Flair UI as posting success.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class OpenFlairDialogNode:
    name = "reddit_open_flair"

    def run(self, context: Any, state: Any) -> Any:
        page = context.require_page(self.name)
        if context.reddit_recognizer is None:
            from Agent.reddit_visual_recognizer import RedditVisualRecognizer

            context.reddit_recognizer = RedditVisualRecognizer(page)

        requirement = context.reddit_recognizer.detect_flair_requirement()
        state.flair_required = bool(requirement.get("required"))
        opened = context.reddit_recognizer._open_flair_dialog()
        if not opened:
            dom_candidates = context.reddit_recognizer.extract_flair_candidates_from_dom()
            state.flair_options = dom_candidates
            if dom_candidates:
                state.add_evidence(
                    self.name,
                    True,
                    "Flair modal data available in real Reddit DOM",
                    subreddit=state.subreddit,
                    flair_requirement=requirement,
                    options=[item.get("text") for item in dom_candidates],
                )
                return state
            if state.flair_required:
                raise PostingWorkflowError(
                    "Flair is required but the dialog could not be opened",
                    node=self.name,
                    code="required_flair_dialog_unavailable",
                    details={"subreddit": state.subreddit, "flair_requirement": requirement},
                )
            state.add_evidence(
                self.name,
                True,
                "Flair dialog not available",
                subreddit=state.subreddit,
                flair_requirement=requirement,
            )
            return state
        state.add_evidence(
            self.name,
            True,
            "Flair dialog opened",
            subreddit=state.subreddit,
            flair_requirement=requirement,
        )
        return state
