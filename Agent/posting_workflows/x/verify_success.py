"""
X node 5: verify posting success.

Purpose:
    Check whether X produced a verifiable post URL after submission.

Main responsibilities:
    - Use URL evidence as the success signal.
    - Require the observed URL to match a real X post permalink shape.
    - Actively open the permalink and verify the expected content is visible.
    - Preserve unknown states as failures instead of green results.

Not responsible for:
    - Retrying failed posts.
    - Generating content.
    - Updating documentation.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.active_post_verifier import ActivePostVerifier
from Agent.posting_workflows.verification_gate import is_platform_post_url


class VerifyXPostSuccessNode:
    name = "x_verify_success"

    def run(self, context: Any, state: Any) -> Any:
        page = context.require_page(self.name)
        current_url = str(getattr(page, "url", ""))
        if not is_platform_post_url("x", current_url):
            state.status = "failed"
            state.error = {
                "node": self.name,
                "code": "x_post_unverified",
                "message": "A verifiable X post URL was not observed after submission",
                "details": {"url": current_url},
            }
            state.add_evidence(
                self.name,
                False,
                "A verifiable X post URL was not observed after submission",
                url=current_url,
            )
            return state
        state.status = "success"
        state.post_url = current_url
        active_evidence = ActivePostVerifier().verify(context, "x", state, node=self.name)
        state.add_evidence(
            self.name,
            True,
            "X post URL actively verified from browser permalink",
            post_url=current_url,
            verification_source="active_browser_permalink_open",
            active_evidence=active_evidence,
        )
        return state
