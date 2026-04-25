"""
Reddit terminal node: update posting document.

Purpose:
    Persist Reddit workflow outcome to the shared social posting ledger.

Main responsibilities:
    - Record success or failure with subreddit, title, URL, and popup analysis.
    - Reject success records unless the dedicated verification node produced evidence.
    - Keep failed attempts visible in the Markdown status table.

Not responsible for:
    - Deciding whether the post succeeded.
    - Retrying failed submissions.
    - Editing Reddit content.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.verification_gate import require_verified_post_success


class UpdateRedditPostingDocumentNode:
    name = "reddit_update_document"

    def run(self, context: Any, state: Any) -> Any:
        ledger = context.require_ledger(self.name)
        verification = None
        if state.status == "success":
            verification = require_verified_post_success("reddit", state, node=self.name)
        status = "Reddit 发帖成功" if state.status == "success" else "Reddit 发帖失败"
        record = ledger.record(
            platform="reddit",
            status=status,
            data={
                "subreddit": state.subreddit,
                "title": state.title,
                "post_url": state.post_url,
                "attempts": state.attempts,
                "verification": verification,
                "popup_analysis": state.last_popup_analysis,
                "error": state.error,
            },
        )
        state.add_evidence(self.name, True, "Reddit posting ledger updated", record=record)
        return state
