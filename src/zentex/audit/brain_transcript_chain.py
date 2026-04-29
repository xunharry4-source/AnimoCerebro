from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.storage_paths import get_storage_paths


ROOT_PARENT_ID = "ROOT"


class TraceEventType(str, Enum):
    THINK_LOOP_STARTED = "think_loop_started"
    PHASE_COMPLETED = "phase_completed"
    COGNITIVE_TOOL_INVOKED = "cognitive_tool_invoked"
    COGNITIVE_TOOL_RESULT = "cognitive_tool_result"
    MEMORY_RECALLED = "memory_recalled"
    CLOUD_AUDIT_REQUESTED = "cloud_audit_requested"
    CLOUD_AUDIT_RESULT = "cloud_audit_result"
    SAFETY_GATE_CHECKED = "safety_gate_checked"
    SAFETY_GATE_BLOCKED = "safety_gate_blocked"
    ACTION_EXECUTED = "action_executed"
    ACTION_RECEIPT = "action_receipt"
    REFLECTION_WRITTEN = "reflection_written"
    EXPERIENCE_PROMOTED = "experience_promoted"
    DELEGATION_SENT = "delegation_sent"
    DELEGATION_RECEIVED = "delegation_received"
    DELEGATION_RECEIPT = "delegation_receipt"


class TraceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1)
    span_id: str = Field(default_factory=lambda: f"span:{uuid4().hex}", min_length=1)
    event_type: TraceEventType
    causal_parent_id: str = Field(min_length=1)
    origin_trace_id: str | None = None
    session_id: str = ""
    turn_id: str = ""
    brain_scope: str = "local"
    decision_type: str = ""
    risk_level: str = "unknown"
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    input_summary: str = ""
    output_summary: str = ""
    blocked: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)

    def normalized(self) -> "TraceSpan":
        started_at = self.started_at or datetime.now(timezone.utc).isoformat()
        return self.model_copy(update={"started_at": started_at})


class TraceSpanAppendResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    idempotent: bool
    span: TraceSpan


class TraceSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str | None = None
    origin_trace_id: str | None = None
    session_id: str | None = None
    decision_type: str | None = None
    risk_level: str | None = None
    started_from: str | None = None
    started_to: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class TraceReplayDiffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_trace_id: str
    right_trace_id: str


class CrossBrainTraceMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_trace_id: str
    local_trace_id: str


class BrainTranscriptChainStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        runtime_dir = get_storage_paths().runtime_data_dir
        self.db_path = Path(db_path or runtime_dir / "brain_transcript_chain.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_chain_spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    causal_parent_id TEXT NOT NULL,
                    origin_trace_id TEXT,
                    session_id TEXT NOT NULL DEFAULT '',
                    turn_id TEXT NOT NULL DEFAULT '',
                    brain_scope TEXT NOT NULL DEFAULT 'local',
                    decision_type TEXT NOT NULL DEFAULT '',
                    risk_level TEXT NOT NULL DEFAULT 'unknown',
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_ms INTEGER,
                    input_summary TEXT NOT NULL DEFAULT '',
                    output_summary TEXT NOT NULL DEFAULT '',
                    blocked INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    span_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chain_trace ON transcript_chain_spans(trace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chain_origin ON transcript_chain_spans(origin_trace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chain_parent ON transcript_chain_spans(causal_parent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chain_started ON transcript_chain_spans(started_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chain_decision ON transcript_chain_spans(decision_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chain_risk ON transcript_chain_spans(risk_level)")
            conn.commit()

    def append_span(self, span: TraceSpan) -> TraceSpanAppendResult:
        normalized = span.normalized()
        self._validate_span(normalized)
        existing = self.get_span(normalized.span_id)
        if existing is not None:
            if existing.model_dump(mode="json") != normalized.model_dump(mode="json"):
                raise ValueError(f"span_id {normalized.span_id} already exists with different content")
            return TraceSpanAppendResult(status="existing", idempotent=True, span=existing)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO transcript_chain_spans (
                    span_id, trace_id, event_type, causal_parent_id, origin_trace_id,
                    session_id, turn_id, brain_scope, decision_type, risk_level,
                    started_at, finished_at, duration_ms, input_summary, output_summary,
                    blocked, payload_json, span_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.span_id,
                    normalized.trace_id,
                    normalized.event_type.value,
                    normalized.causal_parent_id,
                    normalized.origin_trace_id,
                    normalized.session_id,
                    normalized.turn_id,
                    normalized.brain_scope,
                    normalized.decision_type,
                    normalized.risk_level,
                    normalized.started_at,
                    normalized.finished_at,
                    normalized.duration_ms,
                    normalized.input_summary,
                    normalized.output_summary,
                    1 if normalized.blocked else 0,
                    json.dumps(normalized.payload, ensure_ascii=False),
                    json.dumps(normalized.model_dump(mode="json"), ensure_ascii=False),
                ),
            )
            conn.commit()
        return TraceSpanAppendResult(status="created", idempotent=False, span=normalized)

    def _validate_span(self, span: TraceSpan) -> None:
        if not span.trace_id.strip():
            raise ValueError("trace_id is required")
        if not span.causal_parent_id.strip():
            raise ValueError("causal_parent_id is required")
        if span.event_type == TraceEventType.DELEGATION_RECEIVED and not span.origin_trace_id:
            raise ValueError("delegation_received requires origin_trace_id from the sender")
        if span.causal_parent_id != ROOT_PARENT_ID and self.get_span(span.causal_parent_id) is None:
            raise ValueError(f"causal_parent_id {span.causal_parent_id} does not exist")

    def get_span(self, span_id: str) -> TraceSpan | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT span_json FROM transcript_chain_spans WHERE span_id = ?",
                (span_id,),
            ).fetchone()
        if row is None:
            return None
        return TraceSpan.model_validate(json.loads(row["span_json"]))

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        spans = self._spans_for_trace(trace_id)
        if not spans:
            raise KeyError(f"trace_id {trace_id} not found")
        return self._build_trace_payload(trace_id, spans)

    def replay(self, trace_id: str) -> dict[str, Any]:
        payload = self.get_trace(trace_id)
        return {
            "trace_id": trace_id,
            "mode": "timeline",
            "executable_actions_enabled": False,
            "sequence": payload["timeline"],
            "span_count": payload["span_count"],
        }

    def get_span_descendants(self, span_id: str) -> dict[str, Any]:
        root = self.get_span(span_id)
        if root is None:
            raise KeyError(f"span_id {span_id} not found")
        children = self._children_by_parent()
        descendants: list[TraceSpan] = []
        queue: deque[str] = deque(children.get(span_id, []))
        while queue:
            current_id = queue.popleft()
            current = self.get_span(current_id)
            if current is None:
                continue
            descendants.append(current)
            queue.extend(children.get(current_id, []))
        descendants.sort(key=lambda item: str(item.started_at or ""))
        return {
            "span_id": span_id,
            "trace_id": root.trace_id,
            "descendant_count": len(descendants),
            "descendants": [item.model_dump(mode="json") for item in descendants],
        }

    def search(self, filters: TraceSearchFilters) -> dict[str, Any]:
        query = "SELECT span_json FROM transcript_chain_spans WHERE 1=1"
        params: list[Any] = []
        for field in ("trace_id", "origin_trace_id", "session_id", "decision_type", "risk_level"):
            value = getattr(filters, field)
            if value:
                query += f" AND {field} = ?"
                params.append(value)
        if filters.started_from:
            query += " AND started_at >= ?"
            params.append(filters.started_from)
        if filters.started_to:
            query += " AND started_at <= ?"
            params.append(filters.started_to)
        query += " ORDER BY started_at ASC LIMIT ?"
        params.append(filters.limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        spans = [TraceSpan.model_validate(json.loads(row["span_json"])) for row in rows]
        by_trace: dict[str, dict[str, Any]] = {}
        for span in spans:
            item = by_trace.setdefault(
                span.trace_id,
                {
                    "trace_id": span.trace_id,
                    "origin_trace_id": span.origin_trace_id,
                    "session_id": span.session_id,
                    "turn_id": span.turn_id,
                    "span_count": 0,
                    "risk_levels": set(),
                    "decision_types": set(),
                    "first_started_at": span.started_at,
                    "last_started_at": span.started_at,
                },
            )
            item["span_count"] += 1
            item["risk_levels"].add(span.risk_level)
            item["decision_types"].add(span.decision_type)
            item["last_started_at"] = span.started_at
        items = []
        for item in by_trace.values():
            item["risk_levels"] = sorted(item["risk_levels"])
            item["decision_types"] = sorted(value for value in item["decision_types"] if value)
            items.append(item)
        return {"items": items, "span_count": len(spans), "trace_count": len(items)}

    def cross_brain_trace_merge(self, request: CrossBrainTraceMergeRequest) -> dict[str, Any]:
        origin = self.get_trace(request.origin_trace_id)
        local = self.get_trace(request.local_trace_id)
        local_roots = [
            span for span in local["nodes"]
            if span.get("causal_parent_id") == ROOT_PARENT_ID
        ]
        if not any(span.get("origin_trace_id") == request.origin_trace_id for span in local_roots):
            raise ValueError("local trace root does not carry the requested origin_trace_id")
        origin_delegations = [
            span for span in origin["nodes"]
            if span.get("event_type") == TraceEventType.DELEGATION_SENT.value
        ]
        cross_edges = []
        if origin_delegations and local_roots:
            cross_edges.append(
                {
                    "from_span_id": origin_delegations[-1]["span_id"],
                    "to_span_id": local_roots[0]["span_id"],
                    "edge_type": "cross_brain_delegation",
                }
            )
        return {
            "origin_trace_id": request.origin_trace_id,
            "local_trace_id": request.local_trace_id,
            "merged_trace_ids": [request.origin_trace_id, request.local_trace_id],
            "origin": origin,
            "local": local,
            "cross_edges": cross_edges,
        }

    def diff_traces(self, request: TraceReplayDiffRequest) -> dict[str, Any]:
        left = self.get_trace(request.left_trace_id)
        right = self.get_trace(request.right_trace_id)

        def key(span: dict[str, Any]) -> str:
            return f"{span.get('event_type')}::{span.get('input_summary')}"

        left_by_key = {key(span): span for span in left["nodes"]}
        right_by_key = {key(span): span for span in right["nodes"]}
        missing = [left_by_key[item]["span_id"] for item in sorted(set(left_by_key) - set(right_by_key))]
        added = [right_by_key[item]["span_id"] for item in sorted(set(right_by_key) - set(left_by_key))]
        changed = []
        for item in sorted(set(left_by_key) & set(right_by_key)):
            if left_by_key[item].get("output_summary") != right_by_key[item].get("output_summary"):
                changed.append(
                    {
                        "left_span_id": left_by_key[item]["span_id"],
                        "right_span_id": right_by_key[item]["span_id"],
                        "event_key": item,
                        "left_output_summary": left_by_key[item].get("output_summary"),
                        "right_output_summary": right_by_key[item].get("output_summary"),
                    }
                )
        return {
            "left_trace_id": request.left_trace_id,
            "right_trace_id": request.right_trace_id,
            "added_span_ids": added,
            "missing_span_ids": missing,
            "changed_spans": changed,
        }

    def _spans_for_trace(self, trace_id: str) -> list[TraceSpan]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT span_json FROM transcript_chain_spans
                WHERE trace_id = ?
                ORDER BY started_at ASC, span_id ASC
                """,
                (trace_id,),
            ).fetchall()
        return [TraceSpan.model_validate(json.loads(row["span_json"])) for row in rows]

    def _children_by_parent(self) -> dict[str, list[str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT span_id, causal_parent_id FROM transcript_chain_spans ORDER BY started_at ASC"
            ).fetchall()
        children: dict[str, list[str]] = {}
        for row in rows:
            children.setdefault(row["causal_parent_id"], []).append(row["span_id"])
        return children

    def _build_trace_payload(self, trace_id: str, spans: list[TraceSpan]) -> dict[str, Any]:
        nodes = [span.model_dump(mode="json") for span in spans]
        span_ids = {span.span_id for span in spans}
        edges = [
            {
                "from_span_id": span.causal_parent_id,
                "to_span_id": span.span_id,
                "edge_type": "causal_parent",
            }
            for span in spans
            if span.causal_parent_id != ROOT_PARENT_ID and span.causal_parent_id in span_ids
        ]
        roots = [span.span_id for span in spans if span.causal_parent_id == ROOT_PARENT_ID]
        critical_path = self._critical_path(spans)
        audit_span_ids = [
            span.span_id
            for span in spans
            if "audit" in span.event_type.value or "safety_gate" in span.event_type.value
        ]
        blocked_span_ids = [span.span_id for span in spans if span.blocked]
        return {
            "trace_id": trace_id,
            "root_span_ids": roots,
            "span_count": len(spans),
            "nodes": nodes,
            "edges": edges,
            "timeline": nodes,
            "critical_path_span_ids": critical_path,
            "audit_span_ids": audit_span_ids,
            "blocked_span_ids": blocked_span_ids,
        }

    def _critical_path(self, spans: list[TraceSpan]) -> list[str]:
        by_id = {span.span_id: span for span in spans}
        children: dict[str, list[str]] = {}
        for span in spans:
            children.setdefault(span.causal_parent_id, []).append(span.span_id)

        def best_path(span_id: str) -> list[str]:
            child_paths = [best_path(child_id) for child_id in children.get(span_id, []) if child_id in by_id]
            if not child_paths:
                return [span_id]
            child_paths.sort(key=len, reverse=True)
            return [span_id, *child_paths[0]]

        root_paths = [best_path(span.span_id) for span in spans if span.causal_parent_id == ROOT_PARENT_ID]
        if not root_paths:
            return []
        root_paths.sort(key=len, reverse=True)
        return root_paths[0]


def build_default_chain_store() -> BrainTranscriptChainStore:
    return BrainTranscriptChainStore()
