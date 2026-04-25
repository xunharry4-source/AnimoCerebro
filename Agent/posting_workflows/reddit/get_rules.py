"""
Reddit node 3: get community rules.

Purpose:
    Load the selected subreddit's rules before content generation.

Main responsibilities:
    - Use CommunityRulesManager for cached or downloaded rules.
    - Preserve rule source in evidence.

Not responsible for:
    - Validating content against rules.
    - Silently treating missing rules as success.
    - Opening browser pages.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class GetCommunityRulesNode:
    name = "reddit_get_rules"

    def run(self, context: Any, state: Any) -> Any:
        if not state.subreddit:
            raise PostingWorkflowError(
                "Subreddit must be selected before fetching rules",
                node=self.name,
                code="missing_subreddit",
            )
        if context.rules_manager is None:
            from Agent.social_promotion.community_rules_manager import CommunityRulesManager

            context.rules_manager = CommunityRulesManager()

        rule = context.rules_manager.get_community_rules(state.subreddit, auto_download=True)
        if rule is None:
            raise PostingWorkflowError(
                "Community rules unavailable",
                node=self.name,
                code="rules_unavailable",
                details={"subreddit": state.subreddit},
            )
        state.rules = rule.to_dict() if hasattr(rule, "to_dict") else dict(rule)
        state.add_evidence(
            self.name,
            True,
            "Community rules loaded",
            subreddit=state.subreddit,
            source=state.rules.get("source"),
            rule_count=state.rules.get("rule_count"),
        )
        return state
