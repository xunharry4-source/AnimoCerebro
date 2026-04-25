"""
Reddit node 6: analyze Flair popup.

Purpose:
    Read visible Flair options from the open Reddit Flair dialog.

Main responsibilities:
    - Use OCR through RedditVisualRecognizer to extract option candidates.
    - Ask LLM to select the best option semantically for the post/community.

Not responsible for:
    - Clicking the selected Flair.
    - Submitting the Reddit post.
    - Guessing a Flair when neither OCR nor LLM provides evidence.
"""

from __future__ import annotations

import time
from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class AnalyzeFlairPopupNode:
    name = "reddit_analyze_flair_popup"

    def run(self, context: Any, state: Any) -> Any:
        recognizer = context.reddit_recognizer
        if recognizer is None or not recognizer._is_flair_dialog_open():
            if state.flair_required:
                raise PostingWorkflowError(
                    "Flair is required but no dialog is open for analysis",
                    node=self.name,
                    code="required_flair_dialog_missing_for_analysis",
                )
            state.add_evidence(self.name, True, "No Flair dialog to analyze", options=[])
            return state

        screenshot_path = str(recognizer.screenshot_dir / f"reddit_flair_options_{int(time.time())}.png")
        recognizer.page.screenshot(path=screenshot_path, full_page=True)
        candidates = recognizer.extract_visible_flair_candidates(screenshot_path=screenshot_path)
        state.flair_options = candidates
        if not candidates:
            if state.flair_required:
                raise PostingWorkflowError(
                    "Flair is required but no selectable candidates were detected",
                    node=self.name,
                    code="required_flair_candidates_missing",
                    details={"screenshot_path": screenshot_path},
                )
            state.add_evidence(self.name, True, "No Flair candidates detected", screenshot_path=screenshot_path)
            return state

        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Choose the best Reddit Flair option for this post. Return JSON with selected_flair. "
                "Use the exact visible option text from flair_options, including emoji or punctuation. "
                "If no option is appropriate, return selected_flair as an empty string and explain why."
            ),
            context={
                "subreddit": state.subreddit,
                "rules": state.rules,
                "title": state.title,
                "content": state.content,
                "flair_options": [item.get("text") for item in candidates],
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="reddit_flair_selection",
        )
        selected = str(payload.get("selected_flair") or "").strip()
        state.selected_flair = selected or None
        if state.flair_required and not state.selected_flair:
            raise PostingWorkflowError(
                "Flair is required but the LLM did not select an option",
                node=self.name,
                code="required_flair_not_selected",
                details={
                    "flair_options": [item.get("text") for item in candidates],
                    "payload": payload,
                },
            )
        state.add_evidence(
            self.name,
            True,
            "Flair popup analyzed",
            selected_flair=state.selected_flair,
            options=[item.get("text") for item in candidates],
            screenshot_path=screenshot_path,
        )
        return state
