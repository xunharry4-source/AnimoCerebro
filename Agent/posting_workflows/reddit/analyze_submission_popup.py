"""
Reddit node 10: analyze submission popup.

Purpose:
    Interpret Reddit submission result and decide success vs retry.

Main responsibilities:
    - Preserve the popup analysis produced by RedditVisualRecognizer.
    - Mark success only when the submit node verified success.
    - Reject success-like popup results that lack a Reddit post permalink.
    - Leave failed states available for the retry node.

Not responsible for:
    - Rewriting content.
    - Selecting another community.
    - Masking unknown results as success.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.verification_gate import is_platform_post_url


class AnalyzeSubmissionPopupNode:
    name = "reddit_analyze_submission_popup"

    def run(self, context: Any, state: Any) -> Any:
        result = state.last_submission_result or {}
        popup = result.get("popup") if isinstance(result.get("popup"), dict) else {}
        analysis = popup.get("analysis") if isinstance(popup.get("analysis"), dict) else {}
        state.last_popup_analysis = analysis or {
            "status": result.get("status"),
            "summary_zh": result.get("error_message"),
            "category": popup.get("category"),
            "should_retry": popup.get("should_retry", False),
            "needs_flair": popup.get("needs_flair", False),
            "recommended_action": popup.get("recommended_action"),
        }
        if result.get("success"):
            post_url = result.get("post_url")
            if not is_platform_post_url("reddit", post_url, subreddit=state.subreddit):
                raise PostingWorkflowError(
                    "Reddit popup analysis claimed success without a verifiable post URL",
                    node=self.name,
                    code="reddit_popup_success_without_verified_post_url",
                    details={"subreddit": state.subreddit, "post_url": post_url, "result": result},
                )
            state.status = "success"
            state.post_url = post_url
        else:
            state.status = "needs_retry" if state.last_popup_analysis.get("should_retry") else "failed"
        state.add_evidence(
            self.name,
            state.status == "success",
            "Reddit submission popup analyzed",
            status=state.status,
            post_url=state.post_url,
            popup_analysis=state.last_popup_analysis,
        )
        return state
