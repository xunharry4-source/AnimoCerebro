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
        title_input = None
        for selector in [
            'textarea[name="title"]#innerTextArea',
            'textarea[name="title"]',
            'input[name="title"]:not([type="hidden"])',
        ]:
            candidate = page.locator(selector).first
            if candidate.count() > 0 and candidate.is_visible():
                title_input = candidate
                break
        if title_input is None:
            raise PostingWorkflowError(
                "Could not find Reddit title input",
                node=self.name,
                code="reddit_title_input_missing",
            )
        title_input.fill(title)
        try:
            observed_title = title_input.input_value(timeout=3000)
        except Exception:
            observed_title = title_input.evaluate("(node) => node.value || node.textContent || ''")
        if observed_title.strip() != title.strip():
            raise PostingWorkflowError(
                "Reddit title input did not retain the expected title",
                node=self.name,
                code="reddit_title_input_mismatch",
                details={"expected": title, "observed": observed_title},
            )

        composer = page.locator("shreddit-composer").first
        if composer.count() > 0:
            composer.click()
            time.sleep(0.5)
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            page.keyboard.type(content, delay=20)
            self._dismiss_editor_popups(page)
            return

        text_input = page.locator('textarea[name="text"], div[contenteditable="true"]').first
        if text_input.count() <= 0:
            raise PostingWorkflowError(
                "Could not find Reddit content input",
                node=self.name,
                code="reddit_content_input_missing",
            )
        text_input.fill(content)
        self._dismiss_editor_popups(page)

    def _dismiss_editor_popups(self, page: Any) -> None:
        """Close tag suggestion overlays after typing body content."""
        try:
            page.keyboard.press("Escape")
            time.sleep(0.3)
        except Exception as exc:
            raise PostingWorkflowError(
                "Could not send Escape to close Reddit editor popup",
                node=self.name,
                code="reddit_editor_popup_escape_failed",
                details={"error": f"{exc.__class__.__name__}: {exc}"},
            ) from exc
        try:
            point = page.evaluate(
                """
                () => {
                    const composer = document.querySelector('shreddit-composer');
                    const rect = composer?.getBoundingClientRect?.();
                    const width = window.innerWidth || 1280;
                    const height = window.innerHeight || 720;
                    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
                    const y = Math.max(20, Math.min(height - 20, rect.top + Math.min(48, rect.height / 2)));
                    const rightX = rect.right + 24;
                    const leftX = rect.left - 24;
                    const x = rightX < width - 20 ? rightX : Math.max(20, leftX);
                    return { x, y };
                }
                """
            )
            if isinstance(point, dict) and point.get("x") and point.get("y"):
                page.mouse.click(float(point["x"]), float(point["y"]))
                time.sleep(0.3)
        except Exception as exc:
            raise PostingWorkflowError(
                "Could not click beside Reddit editor to close popup",
                node=self.name,
                code="reddit_editor_popup_outside_click_failed",
                details={"error": f"{exc.__class__.__name__}: {exc}"},
            ) from exc
