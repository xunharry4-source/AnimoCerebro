"""
Reddit node 1: get target community list.

Purpose:
    Determine the ordered subreddit list for this posting cycle.

Main responsibilities:
    - Use provided candidates when available.
    - Otherwise ask the active LLM for a target community list.

Not responsible for:
    - Opening Reddit pages.
    - Fetching community rules.
    - Falling back to hidden hard-coded communities after LLM failure.
"""

from __future__ import annotations

from typing import Any, List

from Agent.posting_workflows.errors import PostingWorkflowError


class GetRedditCommunitiesNode:
    name = "reddit_get_communities"

    def __init__(self, default_candidates: List[str] | None = None) -> None:
        self.default_candidates = default_candidates or []

    def run(self, context: Any, state: Any) -> Any:
        if state.community_candidates:
            state.add_evidence(
                self.name,
                True,
                "Using existing community candidates",
                communities=state.community_candidates,
            )
            return state

        if self.default_candidates:
            state.community_candidates = [self._clean(c) for c in self.default_candidates if self._clean(c)]
            state.add_evidence(
                self.name,
                True,
                "Using configured community candidates",
                communities=state.community_candidates,
            )
            return state

        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Choose 3 to 5 Reddit communities suitable for a technical AnimoCerebro post. "
                "Return JSON with communities as an array of subreddit names without r/."
            ),
            context={"project": "AnimoCerebro", "date": context.today.isoformat()},
            node=self.name,
            trace_id=context.trace_id,
            phase="reddit_community_selection",
        )
        communities = payload.get("communities")
        if not isinstance(communities, list):
            raise PostingWorkflowError(
                "LLM did not return communities array",
                node=self.name,
                code="missing_communities",
                details={"payload": payload},
            )
        state.community_candidates = [self._clean(c) for c in communities if self._clean(c)]
        if not state.community_candidates:
            raise PostingWorkflowError(
                "No usable Reddit communities were selected",
                node=self.name,
                code="empty_communities",
            )
        state.add_evidence(self.name, True, "Community candidates selected", communities=state.community_candidates)
        return state

    def _clean(self, subreddit: Any) -> str:
        return str(subreddit or "").strip().replace("r/", "").strip("/")
