"""
Reddit node 9: submit post.

Purpose:
    Submit the already-filled Reddit form through RedditVisualRecognizer.

Main responsibilities:
    - Trigger submission and capture the raw verification result.
    - Reject success-like results that do not include a Reddit post permalink.

Not responsible for:
    - Filling the form (FillRedditFormNode does this).
    - Analyzing the submission popup semantics.
    - Rewriting failed content.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class SubmitRedditPostNode:
    name = "reddit_submit_post"

    def run(self, context: Any, state: Any) -> Any:
        page = context.require_page(self.name)
        recognizer = context.reddit_recognizer
        if recognizer is None:
            from Agent.reddit_visual_recognizer import RedditVisualRecognizer
            recognizer = RedditVisualRecognizer(page)
            context.reddit_recognizer = recognizer
            
        state.attempts += 1
        print(f"   🚀 Submitting Reddit post (Attempt {state.attempts}/{self.context_max_retries(context)})...")
        
        # Submit and verify
        result = recognizer.submit_post_and_verify(
            subreddit=state.subreddit,
            wait_time=20,
        )
        
        state.last_submission_result = result
        
        if result.get("success"):
            post_url = result.get("post_url")
            if not post_url:
                raise PostingWorkflowError(
                    "Reddit claimed success but no post URL was found in evidence",
                    node=self.name,
                    code="reddit_success_without_verified_post_url",
                    details={"subreddit": state.subreddit, "post_url": post_url, "result": result},
                )
            state.status = "success"
            state.post_url = post_url
        else:
            state.status = "failed"
        
        state.add_evidence(
            self.name,
            bool(result.get("success")),
            "Reddit submit attempted",
            result=result,
        )
        return state

    def context_max_retries(self, context: Any) -> int:
        return getattr(context, "max_retries", 3)

    def _fill_form(self, page: Any, title: str, content: str) -> None:
        """Compatibility wrapper for older tests; canonical filling is delegated."""
        from Agent.posting_workflows.reddit.fill_form import FillRedditFormNode

        FillRedditFormNode()._fill_form(page, title, content)
