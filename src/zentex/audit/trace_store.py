from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from zentex.web_console.contracts.audit import (
    AuditPagePayload,
    AuditRecordItem,
    TurnAuditItem,
    TurnAuditPagePayload,
    TurnToolSummaryItem,
)
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.services.audit import (
    build_audit_items,
    build_model_provider_traces,
    build_turn_audit_items,
)

logger = logging.getLogger(__name__)

_UTC = timezone.utc


@dataclass(frozen=True)
class AuditTraceEntry:
    entry_id: str
    trace_id: str
    session_id: str
    turn_id: str
    entry_type: str
    timestamp: datetime
    source: str
    payload: Any


class _StaticAuditEventSource:
    def __init__(self, entries: Sequence[Any]):
        self._entries = list(entries)

    def get_entries_snapshot(self) -> list[Any]:
        return list(self._entries)


class AuditTraceStore:
    """SQLite store for audit-center data.

    Primary purpose: flow health monitoring.
    - `audit_flows` tracks which high-level flows (nine_questions / reflection /
      learning / …) ran, when they started, and whether they completed or failed.
      Modules write directly via record_flow_start / record_flow_end; no transcript
      sync is involved.
    - `model_provider_audit_traces` and the other legacy tables are retained for
      LLM-call tracing.
    """

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._revision_condition = threading.Condition()
        self._revision = 0
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(
                """
                -- ── Flow health monitor ─────────────────────────────────────────────
                -- One row per audit flow.  Upserted on start; updated on end.
                -- Modules write directly via record_flow_start / record_flow_end.
                CREATE TABLE IF NOT EXISTS audit_flows (
                    audit_id TEXT PRIMARY KEY,
                    flow_type TEXT NOT NULL,
                    source_module TEXT NOT NULL DEFAULT '',
                    parent_audit_id TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    question_driver_refs TEXT NOT NULL DEFAULT '[]'
                );

                CREATE INDEX IF NOT EXISTS idx_audit_flows_started_at ON audit_flows(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_flows_flow_type ON audit_flows(flow_type);
                CREATE INDEX IF NOT EXISTS idx_audit_flows_status ON audit_flows(status);
                CREATE INDEX IF NOT EXISTS idx_audit_flows_parent ON audit_flows(parent_audit_id);

                -- ── Legacy / LLM-trace tables (kept for model-provider tracing) ────
                CREATE TABLE IF NOT EXISTS audit_entries (
                    entry_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    question_driver_refs TEXT NOT NULL DEFAULT '[]',
                    context_info TEXT NOT NULL DEFAULT '{}',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    request_id TEXT NOT NULL DEFAULT '',
                    decision_id TEXT NOT NULL DEFAULT '',
                    audit_id TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_audit_entries_timestamp ON audit_entries(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_entries_request_id ON audit_entries(request_id);
                CREATE INDEX IF NOT EXISTS idx_audit_entries_decision_id ON audit_entries(decision_id);
                CREATE INDEX IF NOT EXISTS idx_audit_entries_trace_id ON audit_entries(trace_id);
                -- idx_audit_entries_audit_id is created in the migration block below
                -- (the column may not exist yet on older databases)

                CREATE TABLE IF NOT EXISTS audit_turns (
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    goal_titles TEXT NOT NULL DEFAULT '[]',
                    tool_summaries TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY (session_id, turn_id)
                );

                CREATE INDEX IF NOT EXISTS idx_audit_turns_started_at ON audit_turns(started_at DESC);

                CREATE TABLE IF NOT EXISTS model_provider_audit_traces (
                    request_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    phase_name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    provider_plugin_id TEXT NOT NULL,
                    provider_name TEXT,
                    model TEXT,
                    source_module TEXT,
                    invocation_phase TEXT,
                    question_driver_refs TEXT NOT NULL DEFAULT '[]',
                    invoked_at TEXT,
                    completed_at TEXT,
                    failed_at TEXT,
                    prompt TEXT,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    request_driver_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    related_events_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE INDEX IF NOT EXISTS idx_model_provider_trace_invoked_at
                    ON model_provider_audit_traces(invoked_at DESC);
                """
            )
            # Migrate existing databases: add audit_id column if absent.
            try:
                self._conn.execute(
                    "ALTER TABLE audit_entries ADD COLUMN audit_id TEXT NOT NULL DEFAULT ''"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_audit_entries_audit_id ON audit_entries(audit_id)"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" in str(exc).lower():
                    logger.info("audit_entries.audit_id already exists; skipping migration")
                else:
                    logger.exception("Failed to migrate audit_entries.audit_id column")
                    raise
            try:
                self._conn.execute(
                    "ALTER TABLE audit_entries ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    logger.exception("Failed to migrate audit_entries.payload_json column")
                    raise
            self._conn.commit()

    # ------------------------------------------------------------------
    # Flow health monitor — direct write API
    # ------------------------------------------------------------------

    def record_flow_start(self, audit: Any) -> None:
        """Record that a new audit flow has started.

        Call this at the entry point of any significant system flow
        (nine_questions, reflection, learning, …) before delegating to the
        domain module.  A row is inserted (or ignored if already present so
        that re-entrant calls are safe).
        """
        try:
            with self._lock:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO audit_flows
                        (audit_id, flow_type, source_module, parent_audit_id,
                         status, started_at, question_driver_refs)
                    VALUES (?, ?, ?, ?, 'running', ?, ?)
                    """,
                    (
                        audit.audit_id,
                        audit.flow_type,
                        audit.source_module or "",
                        audit.parent_audit_id,
                        datetime.now(_UTC).isoformat(),
                        json.dumps(list(getattr(audit, "question_driver_refs", []) or [])),
                    ),
                )
                self._conn.commit()
        except Exception as exc:
            logger.warning("record_flow_start failed: %s", exc)

    def record_flow_end(self, audit: Any, *, status: str = "completed") -> None:
        """Record that an audit flow has finished (completed or failed).

        Call this after the domain module returns (or raises).
        ``status`` should be ``"completed"`` or ``"failed"``.
        """
        try:
            with self._lock:
                self._conn.execute(
                    """
                    UPDATE audit_flows
                    SET status = ?, ended_at = ?
                    WHERE audit_id = ?
                    """,
                    (status, datetime.now(_UTC).isoformat(), audit.audit_id),
                )
                self._conn.commit()
        except Exception as exc:
            logger.warning("record_flow_end failed: %s", exc)

    def record_audit_entry(
        self,
        *,
        trace_id: str,
        session_id: str,
        turn_id: str,
        entry_type: str,
        source: str,
        summary: str,
        question_driver_refs: Sequence[Optional[str]] = None,
        context_info: dict[str, Optional[Any]] = None,
        payload: dict[str, Optional[Any]] = None,
        request_id: str = "",
        decision_id: str = "",
    ) -> str:
        entry_id = uuid.uuid4().hex
        normalized_context = dict(context_info or {})
        normalized_payload = dict(payload or {})
        audit_id = self._extract_audit_id(normalized_context) or self._extract_audit_id(normalized_payload)
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO audit_entries (
                    entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, summary,
                    question_driver_refs, context_info, payload_json, request_id, decision_id, audit_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    trace_id,
                    session_id,
                    turn_id,
                    entry_type,
                    datetime.now(_UTC).isoformat(),
                    source,
                    summary,
                    self._json_dump(list(question_driver_refs or []), default="[]"),
                    self._json_dump(normalized_context, default="{}"),
                    self._json_dump(normalized_payload, default="{}"),
                    request_id,
                    decision_id,
                    audit_id,
                ),
            )
            # Keep turn-level audit table hot for query_turn_audit_items read path.
            status = str(
                normalized_context.get("status")
                or normalized_payload.get("status")
                or "completed"
            )
            now_iso = datetime.now(_UTC).isoformat()
            self._conn.execute(
                """
                INSERT INTO audit_turns (
                    session_id, turn_id, started_at, completed_at, status, goal_titles, tool_summaries
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, turn_id) DO UPDATE SET
                    completed_at = excluded.completed_at,
                    status = excluded.status
                """,
                (
                    session_id,
                    turn_id,
                    now_iso,
                    now_iso,
                    status,
                    "[]",
                    "[]",
                ),
            )
            self._conn.commit()
            self._bump_revision()
        return entry_id

    def list_flows(
        self,
        *,
        limit: int = 100,
        flow_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return recent audit flows for the health-monitor UI.

        Each dict contains: audit_id, flow_type, source_module, parent_audit_id,
        status, started_at, ended_at, question_driver_refs.
        """
        where_parts: list[str] = []
        params: list[Any] = []
        if flow_type:
            where_parts.append("flow_type = ?")
            params.append(flow_type)
        if status:
            where_parts.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM audit_flows {where} ORDER BY started_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [
            {
                "audit_id": row["audit_id"],
                "flow_type": row["flow_type"],
                "source_module": row["source_module"],
                "parent_audit_id": row["parent_audit_id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "question_driver_refs": json.loads(row["question_driver_refs"] or "[]"),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers (legacy / LLM-trace sync)
    # ------------------------------------------------------------------

    @staticmethod
    def _json_dump(value: Any, *, default: str = "{}") -> str:
        if value is None:
            return default
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _extract_request_id(payload: dict[str, Any]) -> str:
        return str(payload.get("request_id") or "").strip()

    @staticmethod
    def _extract_decision_id(payload: dict[str, Any]) -> str:
        caller_context = payload.get("caller_context")
        caller_context = caller_context if isinstance(caller_context, dict) else {}
        return str(payload.get("decision_id") or caller_context.get("decision_id") or "").strip()

    @staticmethod
    def _extract_audit_id(payload: dict[str, Any]) -> str:
        """Extract audit_id from FlowAudit-annotated payloads."""
        return str(payload.get("audit_id") or "").strip()

    def sync_from_transcript_entries(self, entries: Iterable[Any]) -> None:
        normalized_entries = list(entries)
        audit_items = build_audit_items(normalized_entries)
        turn_items = build_turn_audit_items(normalized_entries)
        model_provider_traces = build_model_provider_traces(_StaticAuditEventSource(normalized_entries))
        entry_by_id = {str(getattr(entry, "entry_id", "") or ""): entry for entry in normalized_entries}

        with self._lock:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO audit_entries (
                    entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, summary,
                    question_driver_refs, context_info, payload_json, request_id, decision_id, audit_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.entry_id,
                        item.trace_id,
                        item.session_id,
                        item.turn_id,
                        item.entry_type,
                        item.timestamp,
                        item.source,
                        item.summary,
                        self._json_dump(item.question_driver_refs, default="[]"),
                        self._json_dump(item.context_info, default="{}"),
                        self._json_dump(getattr(entry_by_id.get(item.entry_id), "payload", {}), default="{}"),
                        self._extract_request_id(entry_by_id.get(item.entry_id).payload)
                        if isinstance(getattr(entry_by_id.get(item.entry_id), "payload", None), dict)
                        else "",
                        self._extract_decision_id(entry_by_id.get(item.entry_id).payload)
                        if isinstance(getattr(entry_by_id.get(item.entry_id), "payload", None), dict)
                        else "",
                        # audit_id: from FlowAudit.as_payload() embedded in context_info
                        self._extract_audit_id(item.context_info)
                        if isinstance(item.context_info, dict) and item.context_info.get("audit_id")
                        else (
                            self._extract_audit_id(entry_by_id.get(item.entry_id).payload)
                            if isinstance(getattr(entry_by_id.get(item.entry_id), "payload", None), dict)
                            else ""
                        ),
                    )
                    for item in audit_items
                ],
            )
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO audit_turns (
                    session_id, turn_id, started_at, completed_at, status, goal_titles, tool_summaries
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.session_id,
                        item.turn_id,
                        item.started_at,
                        item.completed_at,
                        item.status,
                        self._json_dump(item.goal_titles, default="[]"),
                        self._json_dump([summary.model_dump() for summary in item.tool_summaries], default="[]"),
                    )
                    for item in turn_items
                ],
            )
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO model_provider_audit_traces (
                    request_id, trace_id, decision_id, phase_name, session_id, turn_id, provider_plugin_id,
                    provider_name, model, source_module, invocation_phase, question_driver_refs,
                    invoked_at, completed_at, failed_at, prompt, context_json, request_driver_json,
                    result_json, error_type, error_message, related_events_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.request_id,
                        item.trace_id,
                        item.decision_id,
                        item.phase_name,
                        item.session_id,
                        item.turn_id,
                        item.provider_plugin_id,
                        item.provider_name,
                        item.model,
                        item.source_module,
                        item.invocation_phase,
                        self._json_dump(item.question_driver_refs, default="[]"),
                        item.invoked_at,
                        item.completed_at,
                        item.failed_at,
                        item.prompt,
                        self._json_dump(item.context, default="{}"),
                        self._json_dump(item.request_driver, default="{}"),
                        self._json_dump(item.result, default="null"),
                        item.error_type,
                        item.error_message,
                        self._json_dump([event.model_dump() for event in item.related_events], default="[]"),
                    )
                    for item in model_provider_traces
                ],
            )
            self._conn.commit()
            self._bump_revision()

    def _bump_revision(self) -> None:
        with self._revision_condition:
            self._revision += 1
            self._revision_condition.notify_all()

    def get_revision(self) -> int:
        return self._revision

    def wait_for_revision_after(self, current_revision: int, timeout: float = 3.0) -> bool:
        with self._revision_condition:
            if self._revision > current_revision:
                return True
            self._revision_condition.wait(timeout=timeout)
            return self._revision > current_revision

    @staticmethod
    def _row_to_trace_entry(row: sqlite3.Row) -> AuditTraceEntry:
        timestamp_raw = str(row["timestamp"] or "")
        try:
            timestamp = datetime.fromisoformat(timestamp_raw)
        except ValueError:
            timestamp = datetime.fromtimestamp(0, tz=_UTC)
        return AuditTraceEntry(
            entry_id=str(row["entry_id"]),
            trace_id=str(row["trace_id"]),
            session_id=str(row["session_id"]),
            turn_id=str(row["turn_id"]),
            entry_type=str(row["entry_type"]),
            timestamp=timestamp,
            source=str(row["source"] or "audit"),
            payload=json.loads(row["payload_json"] or "{}"),
        )

    def get_entries_snapshot(self, *, limit: int = 1000) -> list[AuditTraceEntry]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, payload_json
                FROM audit_entries
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_trace_entry(row) for row in rows]

    def read_by_trace_id(self, trace_id: str) -> list[AuditTraceEntry]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, payload_json
                FROM audit_entries
                WHERE trace_id = ?
                ORDER BY timestamp ASC
                """,
                (trace_id,),
            ).fetchall()
        return [self._row_to_trace_entry(row) for row in rows]

    def read_by_turn_id(self, turn_id: str, *, session_id: str | None = None) -> list[AuditTraceEntry]:
        if session_id:
            sql = """
                SELECT entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, payload_json
                FROM audit_entries
                WHERE turn_id = ? AND session_id = ?
                ORDER BY timestamp ASC
            """
            params: tuple[Any, ...] = (turn_id, session_id)
        else:
            sql = """
                SELECT entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, payload_json
                FROM audit_entries
                WHERE turn_id = ?
                ORDER BY timestamp ASC
            """
            params = (turn_id,)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_trace_entry(row) for row in rows]

    def find_intervention_entry(self, idempotency_key: str) -> AuditTraceEntry | None:
        if not idempotency_key:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, payload_json
                FROM audit_entries
                WHERE entry_type = 'human_intervention_applied'
                  AND json_extract(payload_json, '$.idempotency_key') = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (idempotency_key,),
            ).fetchone()
        return self._row_to_trace_entry(row) if row is not None else None

    def list_agent_audit_records(self, agent_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if not agent_id:
            return []
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT timestamp, payload_json
                FROM audit_entries
                WHERE session_id = 'agent-management-audit'
                  AND json_extract(payload_json, '$.agent_id') = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (agent_id, limit),
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in reversed(rows):
            payload = json.loads(row["payload_json"] or "{}")
            records.append(
                {
                    "agent_id": agent_id,
                    "event_type": str(payload.get("event_type") or "UNKNOWN"),
                    "timestamp": str(row["timestamp"] or ""),
                    "summary": str(payload.get("summary") or ""),
                    "details": payload.get("details") if isinstance(payload.get("details"), dict) else {},
                }
            )
        return records

    def list_audit_entries(
        self,
        *,
        page: int = 1,
        page_size: int = 40,
        request_id: Optional[str] = None,
        decision_id: Optional[str] = None,
    ) -> AuditPagePayload:
        page = max(page, 1)
        page_size = max(min(page_size, 200), 1)
        where_parts: list[str] = []
        params: list[Any] = []
        if request_id:
            where_parts.append("request_id = ?")
            params.append(request_id)
        if decision_id:
            where_parts.append("decision_id = ?")
            params.append(decision_id)
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        count_sql = f"SELECT COUNT(*) AS count FROM audit_entries {where_clause}"
        select_sql = f"""
            SELECT entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, summary,
                   question_driver_refs, context_info
            FROM audit_entries
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        with self._lock:
            total_items = int(self._conn.execute(count_sql, tuple(params)).fetchone()["count"])
            total_pages = max((total_items + page_size - 1) // page_size, 1)
            page = min(page, total_pages)
            offset = (page - 1) * page_size
            rows = self._conn.execute(select_sql, (*params, page_size, offset)).fetchall()

        items = [
            AuditRecordItem(
                entry_id=row["entry_id"],
                trace_id=row["trace_id"],
                session_id=row["session_id"],
                turn_id=row["turn_id"],
                entry_type=row["entry_type"],
                timestamp=row["timestamp"],
                source=row["source"],
                summary=row["summary"],
                question_driver_refs=json.loads(row["question_driver_refs"] or "[]"),
                context_info=json.loads(row["context_info"] or "{}"),
            )
            for row in rows
        ]
        return AuditPagePayload(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def list_audit_entries_by_audit_id(self, audit_id: str) -> list[AuditRecordItem]:
        """Return all audit entries belonging to one FlowAudit flow, ordered by time."""
        if not audit_id:
            return []
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entry_id, trace_id, session_id, turn_id, entry_type, timestamp, source, summary,
                       question_driver_refs, context_info
                FROM audit_entries
                WHERE audit_id = ?
                ORDER BY timestamp ASC
                """,
                (audit_id,),
            ).fetchall()
        return [
            AuditRecordItem(
                entry_id=row["entry_id"],
                trace_id=row["trace_id"],
                session_id=row["session_id"],
                turn_id=row["turn_id"],
                entry_type=row["entry_type"],
                timestamp=row["timestamp"],
                source=row["source"],
                summary=row["summary"],
                question_driver_refs=json.loads(row["question_driver_refs"] or "[]"),
                context_info=json.loads(row["context_info"] or "{}"),
            )
            for row in rows
        ]

    def list_turn_audit_items(self, *, page: int = 1, page_size: int = 40) -> TurnAuditPagePayload:
        page = max(page, 1)
        page_size = max(min(page_size, 200), 1)
        with self._lock:
            total_items = int(self._conn.execute("SELECT COUNT(*) AS count FROM audit_turns").fetchone()["count"])
            total_pages = max((total_items + page_size - 1) // page_size, 1)
            page = min(page, total_pages)
            offset = (page - 1) * page_size
            rows = self._conn.execute(
                """
                SELECT session_id, turn_id, started_at, completed_at, status, goal_titles, tool_summaries
                FROM audit_turns
                ORDER BY COALESCE(started_at, completed_at, '') DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()

        items = []
        for row in rows:
            tool_summaries_raw = json.loads(row["tool_summaries"] or "[]")
            items.append(
                TurnAuditItem(
                    turn_id=row["turn_id"],
                    session_id=row["session_id"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    status=row["status"],
                    goal_titles=json.loads(row["goal_titles"] or "[]"),
                    tool_summaries=[TurnToolSummaryItem.model_validate(item) for item in tool_summaries_raw],
                )
            )
        return TurnAuditPagePayload(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def list_model_provider_traces(self) -> list[ModelProviderTraceItem]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM model_provider_audit_traces
                ORDER BY COALESCE(invoked_at, completed_at, failed_at, '') DESC
                """
            ).fetchall()
        return [
            ModelProviderTraceItem(
                trace_id=row["trace_id"],
                request_id=row["request_id"],
                decision_id=row["decision_id"],
                phase_name=row["phase_name"],
                session_id=row["session_id"],
                turn_id=row["turn_id"],
                provider_plugin_id=row["provider_plugin_id"],
                provider_name=row["provider_name"],
                model=row["model"],
                source_module=row["source_module"],
                invocation_phase=row["invocation_phase"],
                question_driver_refs=json.loads(row["question_driver_refs"] or "[]"),
                invoked_at=row["invoked_at"],
                completed_at=row["completed_at"],
                failed_at=row["failed_at"],
                prompt=row["prompt"],
                context=json.loads(row["context_json"] or "{}"),
                request_driver=json.loads(row["request_driver_json"] or "{}"),
                result=json.loads(row["result_json"]) if row["result_json"] else None,
                error_type=row["error_type"],
                error_message=row["error_message"],
                related_events=json.loads(row["related_events_json"] or "[]"),
            )
            for row in rows
        ]
