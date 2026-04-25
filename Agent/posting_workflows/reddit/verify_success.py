"""
Reddit node 11: verify posting success with evidence.

Purpose:
    Make Reddit success verification an explicit workflow node with a real
    platform permalink, active browser inspection, and prior submit/popup evidence.

Main responsibilities:
    - Fail closed when a success state lacks Reddit post evidence.
    - Actively open the Reddit permalink and verify the title is visible.
    - Add a dedicated verification evidence item before documentation can say
      "Reddit 发帖成功".
    - Leave non-success states available for retry/failure routing.

Not responsible for:
    - Publishing the Reddit post.
    - Rewriting failed content.
    - Treating popup text alone as proof of publication.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.active_post_verifier import ActivePostVerifier
from Agent.posting_workflows.verification_gate import require_verified_post_success


class VerifyRedditPostSuccessNode:
    name = "reddit_verify_success"

    def run(self, context: Any, state: Any) -> Any:
        if state.status != "success":
            state.add_evidence(
                self.name,
                False,
                "Reddit post success was not verified because state is not success",
                status=state.status,
                post_url=state.post_url,
            )
            return state

        proof = require_verified_post_success(
            "reddit",
            state,
            node=self.name,
            required_nodes=("reddit_submit_post", "reddit_analyze_submission_popup"),
        )
        active_evidence = ActivePostVerifier().verify(context, "reddit", state, node=self.name)
        state.add_evidence(
            self.name,
            True,
            "Reddit post success actively verified with browser permalink evidence",
            post_url=state.post_url,
            verification_source="active_browser_permalink_open",
            proof=proof,
            active_evidence=active_evidence,
        )
        return state
