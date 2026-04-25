"""
Reddit node 9: submit post.

Purpose:
    Fill the Reddit submit form and submit through RedditVisualRecognizer.

Main responsibilities:
    - Fill title and body into the current Reddit submit page.
    - Trigger submission and capture the raw verification result.
    - Reject success-like results that do not include a Reddit post permalink.

Not responsible for:
    - Analyzing the submission popup semantics.
    - Rewriting failed content.
    - Claiming success without a verified Reddit URL or popup result.
"""

from __future__ import annotations

import time
from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.verification_gate import is_platform_post_url


class SubmitRedditPostNode:
    name = "reddit_submit_post"

    def run(self, context: Any, state: Any) -> Any:
        page = context.require_page(self.name)
        if not state.title or not state.content or not state.subreddit:
            raise PostingWorkflowError(
                "Subreddit, title, and content are required before Reddit submit",
                node=self.name,
                code="missing_submit_content",
            )
        if context.reddit_recognizer is None:
            from Agent.reddit_visual_recognizer import RedditVisualRecognizer

            context.reddit_recognizer = RedditVisualRecognizer(page)

        self._fill_form(page, state.title, state.content)
        state.attempts += 1
        result = context.reddit_recognizer.submit_post_and_verify(
            subreddit=state.subreddit,
            wait_time=20,
            title=state.title,
            content=state.content,
            target_flair=state.selected_flair,
            max_retries=0,
        )
        state.last_submission_result = result
        if result.get("success"):
            post_url = result.get("post_url")
            if not is_platform_post_url("reddit", post_url, subreddit=state.subreddit):
                raise PostingWorkflowError(
                    "Reddit submit result claimed success without a verifiable post URL",
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

    def _fill_form(self, page: Any, title: str, content: str) -> None:
        title_input = page.locator('textarea[name="title"], input[name="title"]').first
        if title_input.count() <= 0:
            raise PostingWorkflowError(
                "Could not find Reddit title input",
                node=self.name,
                code="reddit_title_input_missing",
            )
        title_input.fill(title)

        composer = page.locator("shreddit-composer").first
        if composer.count() > 0:
            composer.click()
            time.sleep(0.5)
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.keyboard.type(content, delay=20)
            return

        text_input = page.locator('textarea[name="text"], div[contenteditable="true"]').first
        if text_input.count() <= 0:
            raise PostingWorkflowError(
                "Could not find Reddit content input",
                node=self.name,
                code="reddit_content_input_missing",
            )
        text_input.fill(content)
