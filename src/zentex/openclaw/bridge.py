from __future__ import annotations

"""Feature 42 openClaw host bridge.

The bridge exposes a constrained protocol for external hosts. It validates the
requested action, records an audit entry, and returns a structured response that
the host can correlate by request_id.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

UTC = timezone.utc
OpenClawAction = Literal["nine_question_query", "task_submit", "reflection_write"]


class OpenClawBridgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    action: OpenClawAction
    payload: dict[str, Any] = Field(default_factory=dict)


class OpenClawBridgeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    host_id: str
    action: OpenClawAction
    accepted: bool
    result: dict[str, Any]
    audited_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OpenClawBridgeRuntime:
    def __init__(self) -> None:
        self._audit: dict[str, OpenClawBridgeResponse] = {}

    def call(self, request: OpenClawBridgeRequest) -> OpenClawBridgeResponse:
        result = _execute_bridge_action(request)
        response = OpenClawBridgeResponse(
            request_id=request.request_id,
            host_id=request.host_id,
            action=request.action,
            accepted=True,
            result=result,
        )
        self._audit[request.request_id] = response
        return response

    def query_audit(self, request_id: str) -> OpenClawBridgeResponse:
        if request_id not in self._audit:
            raise KeyError(request_id)
        return self._audit[request_id]


def _execute_bridge_action(request: OpenClawBridgeRequest) -> dict[str, Any]:
    if request.action == "nine_question_query":
        question = str(request.payload.get("question") or "").strip()
        if not question:
            raise ValueError("nine_question_query requires payload.question")
        return {
            "bridge_protocol": "openclaw.v1",
            "query": question,
            "available_outputs": ["nine_question_frame", "task_candidates", "reflection_hint"],
            "route": "zentex.nine_questions",
        }
    if request.action == "task_submit":
        title = str(request.payload.get("title") or "").strip()
        if not title:
            raise ValueError("task_submit requires payload.title")
        return {
            "bridge_protocol": "openclaw.v1",
            "task_title": title,
            "status": "accepted_for_zentex_task_pipeline",
        }
    if request.action == "reflection_write":
        summary = str(request.payload.get("summary") or "").strip()
        if not summary:
            raise ValueError("reflection_write requires payload.summary")
        return {
            "bridge_protocol": "openclaw.v1",
            "reflection_summary": summary,
            "status": "accepted_for_reflection_pipeline",
        }
    raise ValueError(f"unsupported openClaw action: {request.action}")
