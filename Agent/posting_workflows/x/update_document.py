"""
X node 6: update posting document.

Purpose:
    Record the X posting outcome in the social posting ledger and Markdown table.

Main responsibilities:
    - Persist verified success with topic, content, and URL.
    - Reject success records unless the dedicated verification node produced evidence.
    - Persist failed attempts without marking them as successful.

Not responsible for:
    - Deciding whether X posting succeeded.
    - Editing browser state.
    - Creating post content.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.verification_gate import require_verified_post_success


class UpdateXPostingDocumentNode:
    name = "x_update_document"

    def run(self, context: Any, state: Any) -> Any:
        ledger = context.require_ledger(self.name)
        verification = None
        if state.status == "success":
            verification = require_verified_post_success("x", state, node=self.name)
        status = "X 发帖成功" if state.status == "success" else "X 发帖失败"
        record = ledger.record(
            platform="x",
            status=status,
            data={
                "topic": state.topic,
                "content": state.content,
                "post_url": state.post_url,
                "attempts": state.attempts,
                "verification": verification,
                "error": state.error,
            },
        )
        state.add_evidence(self.name, True, "X posting ledger updated", record=record)
        return state
