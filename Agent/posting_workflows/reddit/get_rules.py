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

        page_rules = self._extract_rules_from_current_page(context)
        if page_rules:
            state.rules = {
                "subreddit": state.subreddit,
                "rules": page_rules,
                "source": "reddit_submit_page_dom",
                "rule_count": len(page_rules),
            }
            state.add_evidence(
                self.name,
                True,
                "Community rules loaded from current Reddit submit page",
                subreddit=state.subreddit,
                source=state.rules["source"],
                rule_count=state.rules["rule_count"],
                titles=[rule.get("title") for rule in page_rules],
            )
            return state

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

    def _extract_rules_from_current_page(self, context: Any) -> list[dict[str, Any]]:
        """Prefer rules already rendered in the open submit page when available."""
        if context.page is None:
            return []
        if context.reddit_recognizer is None:
            from Agent.reddit_visual_recognizer import RedditVisualRecognizer

            context.reddit_recognizer = RedditVisualRecognizer(context.page)

        extractor = getattr(context.reddit_recognizer, "extract_community_rules_from_submit_page_dom", None)
        if extractor is None:
            return []
        rules = extractor()
        if not isinstance(rules, list):
            return []
        return [
            {
                "title": str(rule.get("title") or "").strip(),
                "description": str(rule.get("description") or "").strip(),
                "number": str(rule.get("number") or "").strip(),
                "source": rule.get("source") or "reddit_submit_page_dom",
            }
            for rule in rules
            if isinstance(rule, dict) and rule.get("title") and rule.get("description")
        ]
