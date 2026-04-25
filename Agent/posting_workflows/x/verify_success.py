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

from typing import Any, Optional

from Agent.posting_workflows.active_post_verifier import ActivePostVerifier
from Agent.posting_workflows.verification_gate import is_platform_post_url


class VerifyXPostSuccessNode:
    name = "x_verify_success"

    def run(self, context: Any, state: Any) -> Any:
        page = context.require_page(self.name)
        current_url = str(getattr(page, "url", ""))
        if not is_platform_post_url("x", current_url):
            recovered_url = self._recover_status_url_from_visible_page(page, state)
            if recovered_url:
                current_url = recovered_url
            else:
                state.status = "failed"
                state.error = {
                    "node": self.name,
                    "code": "x_post_unverified",
                    "message": "A verifiable X post URL was not observed after submission",
                    "details": {"url": current_url, "recovery_attempted": True},
                }
                state.add_evidence(
                    self.name,
                    False,
                    "A verifiable X post URL was not observed after submission",
                    url=current_url,
                    recovery_attempted=True,
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

    def _recover_status_url_from_visible_page(self, page: Any, state: Any) -> Optional[str]:
        expected = str(getattr(state, "content", "") or "").strip()
        if len(expected) < 16:
            return None
        for _ in range(2):
            recovered = self._find_status_url_containing_text(page, expected)
            if recovered:
                return recovered
            try:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(8000)
            except Exception:
                return None
        return None

    def _find_status_url_containing_text(self, page: Any, expected: str) -> Optional[str]:
        if not hasattr(page, "evaluate"):
            return None
        script = """
        (expected) => {
          const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const expectedText = normalize(expected);
          const prefix = expectedText.slice(0, Math.min(80, expectedText.length));
          const matchesExpected = (text) => {
            const normalized = normalize(text);
            return normalized.includes(expectedText) || normalized.includes(prefix);
          };
          const toAbsolute = (href) => {
            try { return new URL(href, window.location.origin).href; } catch (_) { return ''; }
          };
          for (const article of Array.from(document.querySelectorAll('article'))) {
            if (!matchesExpected(article.innerText)) continue;
            const link = Array.from(article.querySelectorAll('a[href*="/status/"]'))
              .map((node) => toAbsolute(node.getAttribute('href')))
              .find((href) => /https:\\/\\/(x|twitter)\\.com\\/[^/]+\\/status\\/\\d+/.test(href));
            if (link) return link;
          }
          return null;
        }
        """
        try:
            recovered = page.evaluate(script, expected)
        except Exception:
            return None
        return str(recovered) if recovered else None
