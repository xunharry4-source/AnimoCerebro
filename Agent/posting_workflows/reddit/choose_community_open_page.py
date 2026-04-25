"""
Reddit node 2: choose a community and open its submit page.

Purpose:
    Pick the next unattempted subreddit and navigate to its posting page.

Main responsibilities:
    - Iterate through candidate communities across retries.
    - Open the selected Reddit submit page.

Not responsible for:
    - Fetching rules.
    - Writing content.
    - Handling login or CAPTCHA.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class ChooseCommunityOpenPageNode:
    name = "reddit_choose_community_open_page"

    def run(self, context: Any, state: Any) -> Any:
        page = context.require_page(self.name)
        subreddit = self._next_subreddit(state)
        if not subreddit:
            raise PostingWorkflowError(
                "No unattempted Reddit community remains",
                node=self.name,
                code="no_community_remaining",
                details={
                    "candidates": state.community_candidates,
                    "attempted": state.attempted_communities,
                },
            )
        state.subreddit = subreddit
        if subreddit not in state.attempted_communities:
            state.attempted_communities.append(subreddit)

        url = f"https://www.reddit.com/r/{subreddit}/submit"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not open Reddit submit page: {exc}",
                node=self.name,
                code="reddit_submit_navigation_failed",
                details={"subreddit": subreddit, "url": url},
            ) from exc

        current_url = str(getattr(page, "url", ""))
        if "login" in current_url.lower():
            raise PostingWorkflowError(
                "Reddit session is not logged in",
                node=self.name,
                code="reddit_login_required",
                details={"url": current_url, "subreddit": subreddit},
            )
        state.add_evidence(self.name, True, "Reddit submit page opened", subreddit=subreddit, url=current_url)
        return state

    def _next_subreddit(self, state: Any) -> str | None:
        if state.subreddit and state.status == "retrying_same_community":
            return state.subreddit
        for subreddit in state.community_candidates:
            if subreddit not in state.attempted_communities:
                return subreddit
        return None
