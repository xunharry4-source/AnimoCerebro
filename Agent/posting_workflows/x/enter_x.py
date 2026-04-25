"""
X node 3: enter X.

Purpose:
    Navigate the active browser page to X home/compose context.

Main responsibilities:
    - Open X in the current browser session.
    - Detect obvious unauthenticated redirects.

Not responsible for:
    - Logging into X.
    - Solving CAPTCHA.
    - Writing or submitting content.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class EnterXNode:
    name = "x_enter_x"

    def run(self, context: Any, state: Any) -> Any:
        page = context.require_page(self.name)
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            raise PostingWorkflowError(
                f"Failed to open X: {exc}",
                node=self.name,
                code="x_navigation_failed",
            ) from exc

        current_url = str(getattr(page, "url", ""))
        if "login" in current_url.lower() or "signin" in current_url.lower():
            raise PostingWorkflowError(
                "X session is not logged in",
                node=self.name,
                code="x_login_required",
                details={"url": current_url},
            )
        state.add_evidence(self.name, True, "X opened", url=current_url)
        return state
