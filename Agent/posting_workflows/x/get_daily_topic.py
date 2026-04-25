"""
X node 2: get today's topic.

Purpose:
    Use the active LLM to choose the day's X posting topic.

Main responsibilities:
    - Convert project/date context into a concrete topic and angle.
    - Store topic evidence in XPostingState.

Not responsible for:
    - Writing the final X post.
    - Reading browser state.
    - Falling back to hard-coded topics when LLM fails.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError


class GetDailyTopicNode:
    name = "x_get_daily_topic"

    def run(self, context: Any, state: Any) -> Any:
        payload = context.require_llm(self.name).generate_json(
            prompt=(
                "Choose today's X.com posting topic for the AnimoCerebro project. "
                "Return JSON with topic, angle, audience, and rationale. "
                "The topic must be specific enough for one post."
            ),
            context={
                "date": context.today.isoformat(),
                "project": "AnimoCerebro",
                "platform": "x",
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="x_daily_topic",
        )
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise PostingWorkflowError(
                "LLM did not return a topic",
                node=self.name,
                code="missing_topic",
                details={"payload": payload},
            )
        state.topic = topic
        state.topic_details = payload
        state.add_evidence(self.name, True, "Daily topic selected", topic=topic, payload=payload)
        return state
