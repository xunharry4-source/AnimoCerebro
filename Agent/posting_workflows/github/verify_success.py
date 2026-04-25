"""
GitHub node 5: verify Discussion success.

Purpose:
    Make GitHub Discussion success verification an explicit workflow node.

Main responsibilities:
    - Fail closed when success lacks a GitHub Discussion URL.
    - Require submit evidence before success can be recorded.
    - Attach read-after-write GitHub GraphQL verification evidence.

Not responsible for:
    - Creating the Discussion.
    - Generating title/body.
    - Treating a local URL string as proof without API evidence.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.verification_gate import require_verified_post_success


class VerifyGitHubDiscussionSuccessNode:
    name = "github_verify_success"

    def run(self, context: Any, state: Any) -> Any:
        if state.status != "success":
            state.add_evidence(
                self.name,
                False,
                "GitHub Discussion success was not verified because state is not success",
                status=state.status,
                post_url=state.post_url,
            )
            return state

        proof = require_verified_post_success(
            "github",
            state,
            node=self.name,
            required_nodes=("github_submit_discussion",),
        )
        active_evidence = (state.last_submission_result or {}).get("active_evidence")
        if not active_evidence:
            from Agent.posting_workflows.errors import PostingWorkflowError

            raise PostingWorkflowError(
                "GitHub Discussion success is missing API read-after-write verification evidence",
                node=self.name,
                code="github_active_verification_missing",
                details={"post_url": state.post_url},
            )
        state.add_evidence(
            self.name,
            True,
            "GitHub Discussion success verified with GraphQL read-after-write evidence",
            post_url=state.post_url,
            verification_source="github_graphql_discussion_get",
            proof=proof,
            active_evidence=active_evidence,
        )
        return state
