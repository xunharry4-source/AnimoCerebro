"""
X node 4: write and submit the post.

Purpose:
    Generate X post content with LLM and submit it through the browser.

Main responsibilities:
    - Ask the active ModelProvider for platform-sized content.
    - Fill the X composer and click the post button.

Not responsible for:
    - Verifying final publication.
    - Choosing the daily topic.
    - Using static template text when the LLM fails.
"""

from __future__ import annotations

from typing import Any, Iterable

from Agent.posting_workflows.errors import PostingWorkflowError


class WriteXPostNode:
    name = "x_write_post"

    TEXTBOX_SELECTORS = (
        'div[role="textbox"][data-testid="tweetTextarea_0"]',
        'div[contenteditable="true"][data-testid="tweetTextarea_0"]',
        'div[role="textbox"]',
    )
    POST_BUTTON_SELECTORS = (
        'button[data-testid="tweetButton"]',
        'button[data-testid="tweetButtonInline"]',
        'div[data-testid="tweetButton"]',
        'div[data-testid="tweetButtonInline"]',
        'button:has-text("Post")',
        'div[role="button"]:has-text("Post")',
        'button:has-text("发布")',
    )

    def run(self, context: Any, state: Any) -> Any:
        if not state.topic:
            raise PostingWorkflowError(
                "Daily topic is required before writing X content",
                node=self.name,
                code="missing_topic",
            )
        state.content = self._generate_content(context, state)
        page = context.require_page(self.name)
        self._fill_and_submit(page, state.content)
        state.attempts += 1
        state.add_evidence(self.name, True, "X content submitted", content=state.content)
        return state

    def _generate_content(self, context: Any, state: Any) -> str:
        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Write one X.com post for the given topic. Return JSON with content only. "
                "The content must be <= 260 characters, specific, non-spammy, and useful."
            ),
            context={
                "topic": state.topic,
                "topic_details": state.topic_details,
                "platform": "x",
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="x_content_generation",
        )
        content = str(payload.get("content") or payload.get("post") or payload.get("text") or "").strip()
        if not content:
            raise PostingWorkflowError(
                "LLM did not return X content",
                node=self.name,
                code="missing_content",
                details={"payload": payload},
            )
        if len(content) > 280:
            raise PostingWorkflowError(
                "X content exceeds 280 characters",
                node=self.name,
                code="x_content_too_long",
                details={"length": len(content)},
            )
        return content

    def _fill_and_submit(self, page: Any, content: str) -> None:
        self._open_composer(page)
        textbox = self._first_usable_locator(page, self.TEXTBOX_SELECTORS, require_enabled=False)
        if textbox is None:
            raise PostingWorkflowError(
                "Could not find X composer textbox",
                node=self.name,
                code="x_textbox_missing",
            )
        textbox.click()
        textbox.fill(content)

        button = self._first_usable_locator(page, self.POST_BUTTON_SELECTORS, require_enabled=True)
        if button is None:
            raise PostingWorkflowError(
                "Could not find enabled X post button",
                node=self.name,
                code="x_post_button_missing",
            )
        self._click_post_button(button)
        if hasattr(page, "wait_for_timeout"):
            page.wait_for_timeout(10000)

    def _click_post_button(self, button: Any) -> None:
        try:
            button.click(timeout=10000)
        except Exception as first_exc:
            try:
                button.click(force=True, timeout=5000)
            except Exception as force_exc:
                raise PostingWorkflowError(
                    f"Could not click X post button: {force_exc}",
                    node=self.name,
                    code="x_post_button_click_failed",
                    details={"first_error": str(first_exc)[:500]},
                ) from force_exc

    def _open_composer(self, page: Any) -> None:
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not open X composer: {exc}",
                node=self.name,
                code="x_compose_navigation_failed",
            ) from exc

    def _first_usable_locator(self, page: Any, selectors: Iterable[str], *, require_enabled: bool) -> Any:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if hasattr(locator, "wait_for"):
                    locator.wait_for(state="visible", timeout=8000)
                if locator.count() <= 0:
                    continue
                if hasattr(locator, "is_visible") and not locator.is_visible():
                    continue
                if require_enabled and hasattr(locator, "is_enabled") and not locator.is_enabled():
                    continue
                return locator
            except Exception as exc:
                last_exc = exc
        return None
