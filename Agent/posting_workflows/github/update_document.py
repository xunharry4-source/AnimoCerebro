"""
GitHub node 6: update posting document.

Purpose:
    Record the GitHub Discussion posting outcome in the social posting ledger.

Main responsibilities:
    - Persist verified GitHub Discussion success with repository, category, discussion number, and URL.
    - Reject success rows unless the verification node produced evidence.
    - Persist failure rows without marking them successful.

Not responsible for:
    - Deciding whether GitHub posting succeeded.
    - Creating or editing GitHub Discussions.
    - Hiding token, permission, or API failures.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.verification_gate import require_verified_post_success


class UpdateGitHubPostingDocumentNode:
    name = "github_update_document"

    def run(self, context: Any, state: Any) -> Any:
        ledger = context.require_ledger(self.name)
        verification = None
        if state.status == "success":
            verification = require_verified_post_success("github", state, node=self.name)
        status = "GitHub 发帖成功" if state.status == "success" else "GitHub 发帖失败"
        record = ledger.record(
            platform="github",
            status=status,
            data={
                "repository": state.repository,
                "title": state.title,
                "content": state.content,
                "category_id": state.category_id,
                "category_name": state.category_name,
                "discussion_id": state.discussion_id,
                "discussion_number": state.discussion_number,
                "post_url": state.post_url,
                "attempts": state.attempts,
                "verification": verification,
                "error": state.error,
            },
        )
        state.add_evidence(self.name, True, "GitHub posting ledger updated", record=record)
        return state
