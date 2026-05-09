from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


UTC = timezone.utc


@dataclass(frozen=True)
class LLMUsageEvent:
    event_id: str
    timestamp: str
    provider_key: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    source_module: str = ""
    invocation_phase: str = ""
    decision_id: str = ""
    trace_id: str = ""
    call_type: str = "generate_json"
    caller_context: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    raw_usage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "provider_key": self.provider_key,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "source_module": self.source_module,
            "invocation_phase": self.invocation_phase,
            "decision_id": self.decision_id,
            "trace_id": self.trace_id,
            "call_type": self.call_type,
            "caller_context": dict(self.caller_context or {}),
            "metadata": dict(self.metadata or {}),
            "raw_usage": dict(self.raw_usage or {}),
        }


class LLMUsageStore:
    """Durable token usage ledger stored in the dedicated LLM database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else self.default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    @staticmethod
    def default_db_path() -> Path:
        env_path = str(
            os.environ.get("ZENTEX_LLM_DB")
            or os.environ.get("ZENTEX_LLM_USAGE_DB")
            or ""
        ).strip()
        if env_path:
            return Path(env_path)
        from zentex.common.storage_paths import get_storage_paths

        return get_storage_paths().app_data_dir / "llm" / "llm.sqlite3"

    def close(self) -> None:
        with self._lock:
            conn = getattr(self, "_conn", None)
            if conn is None:
                return
            try:
                conn.close()
            finally:
                self._conn = None

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS llm_usage_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    source_module TEXT NOT NULL DEFAULT '',
                    invocation_phase TEXT NOT NULL DEFAULT '',
                    decision_id TEXT NOT NULL DEFAULT '',
                    trace_id TEXT NOT NULL DEFAULT '',
                    call_type TEXT NOT NULL DEFAULT 'generate_json',
                    caller_context_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    raw_usage_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_llm_usage_timestamp ON llm_usage_events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_provider ON llm_usage_events(provider_key);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage_events(model);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_provider_model ON llm_usage_events(provider_key, model);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_source_module ON llm_usage_events(source_module);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_decision_id ON llm_usage_events(decision_id);
                CREATE INDEX IF NOT EXISTS idx_llm_usage_trace_id ON llm_usage_events(trace_id);
                """
            )
            self._conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _safe_json(payload: Any) -> str:
        try:
            normalized = payload if isinstance(payload, dict) else {}
            return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return json.dumps({"repr": repr(payload)}, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _context_to_dict(caller_context: Any) -> dict[str, Any]:
        if caller_context is None:
            return {}
        if hasattr(caller_context, "model_dump") and callable(caller_context.model_dump):
            dumped = caller_context.model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else {}
        if isinstance(caller_context, dict):
            return dict(caller_context)
        try:
            return dict(caller_context)
        except Exception:
            return {}

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> LLMUsageEvent:
        return LLMUsageEvent(
            event_id=str(row["event_id"]),
            timestamp=str(row["timestamp"]),
            provider_key=str(row["provider_key"]),
            model=str(row["model"]),
            input_tokens=int(row["input_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
            total_tokens=int(row["total_tokens"] or 0),
            source_module=str(row["source_module"] or ""),
            invocation_phase=str(row["invocation_phase"] or ""),
            decision_id=str(row["decision_id"] or ""),
            trace_id=str(row["trace_id"] or ""),
            call_type=str(row["call_type"] or "generate_json"),
            caller_context=json.loads(row["caller_context_json"] or "{}"),
            metadata=json.loads(row["metadata_json"] or "{}"),
            raw_usage=json.loads(row["raw_usage_json"] or "{}"),
        )

    def record_usage(
        self,
        *,
        provider_key: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        caller_context: Any = None,
        metadata: Optional[dict[str, Any]] = None,
        raw_usage: Optional[dict[str, Any]] = None,
        call_type: str = "generate_json",
        timestamp: Optional[datetime] = None,
        event_id: Optional[str] = None,
    ) -> LLMUsageEvent:
        context = self._context_to_dict(caller_context)
        event = LLMUsageEvent(
            event_id=event_id or f"llm-usage-{uuid.uuid4().hex}",
            timestamp=(timestamp.astimezone(UTC).isoformat() if timestamp else self._now_iso()),
            provider_key=str(provider_key or "").strip(),
            model=str(model or "").strip(),
            input_tokens=max(0, int(input_tokens or 0)),
            output_tokens=max(0, int(output_tokens or 0)),
            total_tokens=max(0, int(total_tokens or 0)),
            source_module=str(context.get("source_module") or ""),
            invocation_phase=str(context.get("invocation_phase") or ""),
            decision_id=str(context.get("decision_id") or ""),
            trace_id=str(context.get("trace_id") or ""),
            call_type=str(call_type or "generate_json"),
            caller_context=context,
            metadata=dict(metadata or {}),
            raw_usage=dict(raw_usage or {}),
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO llm_usage_events
                (
                    event_id, timestamp, provider_key, model,
                    input_tokens, output_tokens, total_tokens,
                    source_module, invocation_phase, decision_id, trace_id,
                    call_type, caller_context_json, metadata_json, raw_usage_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.provider_key,
                    event.model,
                    event.input_tokens,
                    event.output_tokens,
                    event.total_tokens,
                    event.source_module,
                    event.invocation_phase,
                    event.decision_id,
                    event.trace_id,
                    event.call_type,
                    self._safe_json(event.caller_context),
                    self._safe_json(event.metadata),
                    self._safe_json(event.raw_usage),
                ),
            )
            self._conn.commit()
        return event

    def stats_snapshot(self) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS request_count,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens
                FROM llm_usage_events
                """
            ).fetchone()
        return {
            "request_count": int(row["request_count"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "total_tokens": int(row["total_tokens"] or 0),
        }

    def aggregated_stats(self) -> dict[str, Any]:
        snapshot = self.stats_snapshot()
        return {
            "total_request_count": snapshot["request_count"],
            "total_input_tokens": snapshot["input_tokens"],
            "total_output_tokens": snapshot["output_tokens"],
            "total_tokens": snapshot["total_tokens"],
            "providers": self.grouped_stats("provider_key"),
            "models": self.grouped_stats("model"),
            "provider_models": self.grouped_stats("provider_key, model"),
            "db_path": str(self.db_path),
        }

    def grouped_stats(self, group_by: str) -> dict[str, dict[str, int]]:
        allowed = {
            "provider_key": ("provider_key",),
            "model": ("model",),
            "provider_key, model": ("provider_key", "model"),
        }
        columns = allowed.get(group_by)
        if columns is None:
            raise ValueError(f"Unsupported LLM usage group_by: {group_by}")
        select_columns = ", ".join(columns)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT
                    {select_columns},
                    COUNT(*) AS request_count,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens
                FROM llm_usage_events
                GROUP BY {select_columns}
                ORDER BY total_tokens DESC, request_count DESC
                """
            ).fetchall()
        result: dict[str, dict[str, int]] = {}
        for row in rows:
            key = "/".join(str(row[column] or "") for column in columns)
            result[key] = {
                "request_count": int(row["request_count"] or 0),
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
                "total_tokens": int(row["total_tokens"] or 0),
                "error_count": 0,
            }
        return result

    def list_usage_events(
        self,
        *,
        limit: int = 100,
        provider_key: Optional[str] = None,
        model: Optional[str] = None,
        source_module: Optional[str] = None,
    ) -> list[LLMUsageEvent]:
        filters: list[str] = []
        params: list[Any] = []
        if provider_key:
            filters.append("provider_key = ?")
            params.append(provider_key)
        if model:
            filters.append("model = ?")
            params.append(model)
        if source_module:
            filters.append("source_module = ?")
            params.append(source_module)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(max(1, int(limit or 100)))
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT *
                FROM llm_usage_events
                {where}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]
