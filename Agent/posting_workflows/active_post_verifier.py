"""
Active browser verifier for published social posts.

Purpose:
    Actively open a platform permalink after posting and collect browser-visible
    evidence that the post page exists and contains the expected content.

Main responsibilities:
    - Navigate to X or Reddit post URLs with the active browser page.
    - Reject redirects, unavailable pages, and pages that do not show expected text.
    - Return structured evidence suitable for workflow audit records.

Not responsible for:
    - Publishing or editing posts.
    - Translating platform errors.
    - Downgrading missing evidence into success.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.verification_gate import is_platform_post_url


class ActivePostVerifier:
    """Open the permalink and verify platform-visible post evidence."""

    UNAVAILABLE_MARKERS = {
        "x": (
            "this post is unavailable",
            "this post was deleted",
            "this page doesn’t exist",
            "this page doesn't exist",
            "account suspended",
            "something went wrong",
            "retry",
        ),
        "reddit": (
            "sorry, this post was deleted",
            "this post has been removed",
            "page not found",
            "404",
            "sorry, there aren’t any communities",
            "sorry, there aren't any communities",
        ),
    }

    def __init__(self, *, navigation_timeout_ms: int = 30000, text_timeout_ms: int = 8000) -> None:
        self.navigation_timeout_ms = navigation_timeout_ms
        self.text_timeout_ms = text_timeout_ms

    def verify(self, context: Any, platform: str, state: Any, *, node: str) -> Dict[str, Any]:
        page = context.require_page(node)
        post_url = getattr(state, "post_url", None)
        subreddit = getattr(state, "subreddit", None)
        if not is_platform_post_url(platform, post_url, subreddit=subreddit):
            raise PostingWorkflowError(
                "Active verification requires a valid platform permalink",
                node=node,
                code="active_verification_url_invalid",
                details={"platform": platform, "post_url": post_url, "subreddit": subreddit},
            )

        response_status = self._open_permalink(page, post_url, node=node)
        observed_url = str(getattr(page, "url", "") or "")
        if not is_platform_post_url(platform, observed_url, subreddit=subreddit):
            raise PostingWorkflowError(
                "Active verification did not remain on a platform post permalink",
                node=node,
                code="active_verification_redirected",
                details={"platform": platform, "post_url": post_url, "observed_url": observed_url},
            )

        title = self._read_title(page, node=node)
        body_text = self._read_body_text(page, node=node)
        self._reject_unavailable_page(platform, title, body_text, node=node, post_url=post_url)
        expected_text = self._expected_text(platform, state, node=node)
        if not self._text_matches(body_text, expected_text):
            raise PostingWorkflowError(
                "Active verification could not find expected post text on the permalink page",
                node=node,
                code="active_verification_content_missing",
                details={
                    "platform": platform,
                    "post_url": post_url,
                    "expected_text": expected_text[:160],
                    "page_title": title[:200],
                    "body_snippet": body_text[:500],
                },
            )

        return {
            "verification_source": "active_browser_permalink_open",
            "post_url": post_url,
            "observed_url": observed_url,
            "response_status": response_status,
            "page_title": title[:200],
            "body_snippet": body_text[:500],
            "expected_text": expected_text[:160],
            "content_match": True,
        }

    def _open_permalink(self, page: Any, post_url: str, *, node: str) -> Optional[int]:
        if not hasattr(page, "goto"):
            raise PostingWorkflowError(
                "Browser page does not support active permalink navigation",
                node=node,
                code="active_verification_page_unsupported",
                details={"post_url": post_url},
            )
        try:
            response = page.goto(post_url, wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
        except Exception as exc:
            raise PostingWorkflowError(
                f"Active permalink navigation failed: {exc}",
                node=node,
                code="active_verification_navigation_failed",
                details={"post_url": post_url},
            ) from exc
        status = self._response_status(response)
        if status is not None and status >= 400:
            raise PostingWorkflowError(
                "Active permalink navigation returned an HTTP error",
                node=node,
                code="active_verification_http_error",
                details={"post_url": post_url, "status": status},
            )
        return status

    def _read_title(self, page: Any, *, node: str) -> str:
        try:
            title = page.title() if hasattr(page, "title") else ""
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not read page title during active verification: {exc}",
                node=node,
                code="active_verification_title_read_failed",
            ) from exc
        return str(title or "")

    def _read_body_text(self, page: Any, *, node: str) -> str:
        if not hasattr(page, "locator"):
            raise PostingWorkflowError(
                "Browser page does not support body text inspection",
                node=node,
                code="active_verification_text_unsupported",
            )
        try:
            body = page.locator("body")
            body_text = body.inner_text(timeout=self.text_timeout_ms)
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not read body text during active verification: {exc}",
                node=node,
                code="active_verification_text_read_failed",
            ) from exc
        body_text = str(body_text or "").strip()
        if not body_text:
            raise PostingWorkflowError(
                "Active verification found an empty post page body",
                node=node,
                code="active_verification_body_empty",
            )
        return body_text

    def _reject_unavailable_page(self, platform: str, title: str, body_text: str, *, node: str, post_url: str) -> None:
        haystack = self._normalize(f"{title}\n{body_text}")
        for marker in self.UNAVAILABLE_MARKERS.get(platform, ()):
            if marker in haystack:
                raise PostingWorkflowError(
                    "Active verification found a platform unavailable/deleted marker",
                    node=node,
                    code="active_verification_unavailable_marker",
                    details={"platform": platform, "post_url": post_url, "marker": marker},
                )

    def _expected_text(self, platform: str, state: Any, *, node: str) -> str:
        expected = getattr(state, "content", None) if platform == "x" else getattr(state, "title", None)
        expected = str(expected or "").strip()
        if len(expected) < 8:
            raise PostingWorkflowError(
                "Active verification requires enough expected post text to compare",
                node=node,
                code="active_verification_expected_text_missing",
                details={"platform": platform},
            )
        return expected

    def _text_matches(self, body_text: str, expected_text: str) -> bool:
        normalized_body = self._normalize(body_text)
        normalized_expected = self._normalize(expected_text)
        return normalized_expected in normalized_body

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()

    def _response_status(self, response: Any) -> Optional[int]:
        if response is None:
            return None
        status = getattr(response, "status", None)
        return int(status) if isinstance(status, int) else None
