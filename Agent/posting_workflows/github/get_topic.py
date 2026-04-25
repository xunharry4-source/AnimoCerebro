"""
GitHub node 2: get Discussion topic.

Purpose:
    Use the active LLM to choose a GitHub Discussion topic for the target repository.

Main responsibilities:
    - Convert project/date context into a concrete GitHub Discussion topic.
    - Store topic metadata for later Discussion title/body generation.

Not responsible for:
    - Creating the Discussion.
    - Falling back to a static topic when the LLM is unavailable.
    - Verifying GitHub permissions.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class GetGitHubTopicNode:
    name = "github_get_topic"

    def run(self, context: Any, state: Any) -> Any:
        if not state.repository:
            raise PostingWorkflowError(
                "GitHub repository is required before topic generation",
                node=self.name,
                code="github_repository_missing",
            )
        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Choose one GitHub Discussion topic for the AnimoCerebro repository. "
                "Return JSON with topic, discussion_type, audience, rationale, and category_name. "
                "The topic must be suitable for a public project Discussion or announcement."
            ),
            context={
                "date": context.today.isoformat(),
                "project": "AnimoCerebro",
                "platform": "github",
                "repository": state.repository,
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="github_discussion_topic",
        )
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise PostingWorkflowError(
                "LLM did not return a GitHub Discussion topic",
                node=self.name,
                code="github_topic_missing",
                details={"payload": payload},
            )
        category_name = str(payload.get("category_name") or "").strip()
        state.topic = topic
        if category_name:
            state.category_name = category_name
        state.add_evidence(self.name, True, "GitHub Discussion topic selected", topic=topic, payload=payload)
        return state
