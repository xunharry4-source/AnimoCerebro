"""
Shared browser opening node.

Purpose:
    Create or reuse a Playwright page for social posting workflows.

Main responsibilities:
    - Reuse an injected page when tests or callers provide one.
    - Start BrowserAutomationManager for real workflow runs.

Not responsible for:
    - Logging into X or Reddit.
    - Bypassing bot checks or CAPTCHA.
    - Closing browser sessions owned by the caller.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class OpenBrowserNode:
    name = "open_browser"

    def run(self, context: Any, state: Any) -> Any:
        if context.page is not None:
            state.add_evidence(self.name, True, "Reused injected browser page")
            return state

        try:
            from Agent.browser_automation.browser_automation import BrowserAutomationManager
        except Exception as exc:
            raise PostingWorkflowError(
                f"Browser automation unavailable: {exc}",
                node=self.name,
                code="browser_import_failed",
            ) from exc

        try:
            manager = BrowserAutomationManager(headless=False, slow_mo=500)
            manager.start_browser("chromium")
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not open browser: {exc}",
                node=self.name,
                code="browser_start_failed",
            ) from exc

        context.browser_manager = manager
        context.page = manager.page
        state.add_evidence(self.name, True, "Browser opened")
        return state
