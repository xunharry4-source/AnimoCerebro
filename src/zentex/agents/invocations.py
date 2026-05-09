from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from zentex.agents.auth import redact_sensitive
from zentex.common.database import DatabaseConnection
from zentex.common.storage_paths import get_storage_paths


UTC = timezone.utc


def new_external_task_ref() -> str:
    return f"ztx_taskref_{secrets.token_urlsafe(18).replace('-', '').replace('_', '')}"


def new_callback_token() -> str:
    return secrets.token_urlsafe(32)


def hash_callback_token(token: str | None) -> str:
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AgentInvocationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_task_ref: str
    invocation_id: str
    agent_id: str
    zentex_task_id: str | None = None
    trace_id: str = ""
    adapter_type: str = "legacy_bridge"
    status: str = "started"
    request_payload: dict[str, Any] = Field(default_factory=dict)
    normalized_result: Any = None
    raw_response: Any = None
    verification: Any = None
    callback_token_hash: str = ""
    callback_url: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class AgentInvocationLedger:
    """SQLite-backed ledger for Zentex-local external Agent invocations."""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db
        self.ensure_schema()

    @classmethod
    def default(cls) -> "AgentInvocationLedger":
        return cls(DatabaseConnection(str(get_storage_paths().core_db)))

    def ensure_schema(self) -> None:
        with self.db.get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_invocations (
                    external_task_ref TEXT PRIMARY KEY,
                    invocation_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    zentex_task_id TEXT,
                    trace_id TEXT,
                    adapter_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_payload_json TEXT NOT NULL DEFAULT '{}',
                    normalized_result_json TEXT,
                    raw_response_json TEXT,
                    verification_json TEXT,
                    callback_token_hash TEXT,
                    callback_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_invocations_invocation_id
                    ON agent_invocations(invocation_id);
                CREATE INDEX IF NOT EXISTS idx_agent_invocations_agent_id
                    ON agent_invocations(agent_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_invocations_zentex_task_id
                    ON agent_invocations(zentex_task_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_invocations_status
                    ON agent_invocations(status, updated_at DESC);
                """
            )

    def create_started(
        self,
        *,
        external_task_ref: str,
        invocation_id: str,
        agent_id: str,
        zentex_task_id: str | None,
        trace_id: str,
        adapter_type: str,
        request_payload: dict[str, Any],
        callback_token: str | None = None,
        callback_url: str | None = None,
    ) -> AgentInvocationRecord:
        now = _now()
        self.db.execute_update(
            """
            INSERT INTO agent_invocations (
                external_task_ref, invocation_id, agent_id, zentex_task_id,
                trace_id, adapter_type, status, request_payload_json,
                callback_token_hash, callback_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                external_task_ref,
                invocation_id,
                agent_id,
                zentex_task_id,
                trace_id,
                adapter_type,
                "started",
                _json(redact_sensitive(request_payload)),
                hash_callback_token(callback_token),
                callback_url,
                now,
                now,
            ),
        )
        return self.get_by_external_task_ref(external_task_ref)  # type: ignore[return-value]

    def update_result(
        self,
        external_task_ref: str,
        *,
        status: str,
        normalized_result: Any = None,
        raw_response: Any = None,
        verification: Any = None,
    ) -> AgentInvocationRecord | None:
        now = _now()
        completed_at = now if status in {"completed", "failed", "uncertain"} else None
        self.db.execute_update(
            """
            UPDATE agent_invocations
            SET status = ?,
                normalized_result_json = ?,
                raw_response_json = ?,
                verification_json = ?,
                updated_at = ?,
                completed_at = COALESCE(?, completed_at)
            WHERE external_task_ref = ?
            """,
            (
                status,
                _json_or_none(redact_sensitive(normalized_result)),
                _json_or_none(redact_sensitive(raw_response)),
                _json_or_none(redact_sensitive(verification)),
                now,
                completed_at,
                external_task_ref,
            ),
        )
        return self.get_by_external_task_ref(external_task_ref)

    def update_callback(
        self,
        external_task_ref: str,
        *,
        token: str,
        status: str,
        trace_id: str | None = None,
        normalized_result: Any = None,
        raw_response: Any = None,
    ) -> AgentInvocationRecord | None:
        record = self.get_by_external_task_ref(external_task_ref)
        if record is None:
            return None
        if record.callback_token_hash and not secrets.compare_digest(record.callback_token_hash, hash_callback_token(token)):
            raise PermissionError("Invalid callback token")
        if trace_id and record.trace_id and record.trace_id != trace_id:
            raise ValueError("Callback trace_id does not match invocation ledger")
        return self.update_result(
            external_task_ref,
            status=status,
            normalized_result=normalized_result,
            raw_response=raw_response,
        )

    def get_by_external_task_ref(self, external_task_ref: str) -> AgentInvocationRecord | None:
        rows = self.db.execute_query(
            "SELECT * FROM agent_invocations WHERE external_task_ref = ? LIMIT 1",
            (external_task_ref,),
        )
        return self._row_to_record(rows[0]) if rows else None

    def list_by_agent_id(self, agent_id: str, *, limit: int = 100) -> list[AgentInvocationRecord]:
        rows = self.db.execute_query(
            """
            SELECT * FROM agent_invocations
            WHERE agent_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (agent_id, limit),
        )
        return [self._row_to_record(row) for row in rows]

    def list_by_zentex_task_id(self, zentex_task_id: str, *, limit: int = 100) -> list[AgentInvocationRecord]:
        rows = self.db.execute_query(
            """
            SELECT * FROM agent_invocations
            WHERE zentex_task_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (zentex_task_id, limit),
        )
        return [self._row_to_record(row) for row in rows]

    def _row_to_record(self, row: Any) -> AgentInvocationRecord:
        data = dict(row)
        return AgentInvocationRecord(
            external_task_ref=data["external_task_ref"],
            invocation_id=data["invocation_id"],
            agent_id=data["agent_id"],
            zentex_task_id=data.get("zentex_task_id"),
            trace_id=data.get("trace_id") or "",
            adapter_type=data.get("adapter_type") or "legacy_bridge",
            status=data.get("status") or "started",
            request_payload=_loads(data.get("request_payload_json"), {}),
            normalized_result=_loads(data.get("normalized_result_json"), None),
            raw_response=_loads(data.get("raw_response_json"), None),
            verification=_loads(data.get("verification_json"), None),
            callback_token_hash=data.get("callback_token_hash") or "",
            callback_url=data.get("callback_url"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            completed_at=data.get("completed_at"),
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return _json(value)


def _loads(value: str | None, default: Any) -> Any:
    if value in {None, ""}:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
