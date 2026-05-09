from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from zentex.common.storage_paths import get_storage_paths


_TABLES: dict[str, tuple[str, str, str]] = {
    "agent": ("agent_registrations", "agent_registration_history", "agent_runtime_logs"),
    "cli": ("cli_tool_registrations", "cli_tool_registration_history", "cli_tool_runtime_logs"),
    "mcp": ("mcp_server_registrations", "mcp_server_registration_history", "mcp_server_runtime_logs"),
    "external_connector": (
        "external_connector_registrations",
        "external_connector_registration_history",
        "external_connector_runtime_logs",
    ),
}

_SENSITIVE_KEY_TOKENS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "password",
    "secret",
    "token",
)
_SAFE_REFERENCE_KEYS = {
    "credential_id",
    "credential_ref",
    "credential_type",
    "owner_id",
    "owner_type",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key not in _SAFE_REFERENCE_KEYS and any(
                token in normalized_key for token in _SENSITIVE_KEY_TOKENS
            ):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class ExternalCapabilityRegistryStore:
    """Independent DB tables for registered Agents, CLI tools, MCP servers, and connectors."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else get_storage_paths().core_db
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def table_names(kind: str) -> tuple[str, str, str]:
        try:
            return _TABLES[kind]
        except KeyError as exc:
            raise ValueError(f"unsupported external capability kind: {kind}") from exc

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            for current_table, history_table, runtime_table in _TABLES.values():
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {current_table} (
                        asset_id TEXT PRIMARY KEY,
                        display_name TEXT,
                        status TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        deleted_at TEXT
                    )
                    """
                )
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {history_table} (
                        event_id TEXT PRIMARY KEY,
                        asset_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        operator_id TEXT,
                        trace_id TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {runtime_table} (
                        log_id TEXT PRIMARY KEY,
                        asset_id TEXT NOT NULL,
                        capability_name TEXT,
                        invocation_type TEXT,
                        status TEXT NOT NULL,
                        request_json TEXT NOT NULL,
                        response_json TEXT,
                        error_message TEXT,
                        trace_id TEXT,
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        duration_ms INTEGER
                    )
                    """
                )
            conn.commit()

    def upsert_current(
        self,
        kind: str,
        asset_id: str,
        payload: dict[str, Any],
        *,
        status: str = "active",
        display_name: str | None = None,
        action: str = "upsert",
        operator_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        current_table, _, _ = self.table_names(kind)
        now = _utc_now()
        safe_payload = _redact(payload)
        payload_json = json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT created_at FROM {current_table} WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            created_at = str(row["created_at"]) if row else now
            conn.execute(
                f"""
                INSERT INTO {current_table} (
                    asset_id, display_name, status, payload_json, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(asset_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at,
                    deleted_at = NULL
                """,
                (asset_id, display_name, status, payload_json, created_at, now),
            )
            conn.commit()
        self.append_history(
            kind,
            asset_id,
            action=action,
            payload=safe_payload,
            operator_id=operator_id,
            trace_id=trace_id,
            created_at=now,
        )

    def delete_current(
        self,
        kind: str,
        asset_id: str,
        *,
        payload: dict[str, Any] | None = None,
        operator_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        current_table, _, _ = self.table_names(kind)
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(f"DELETE FROM {current_table} WHERE asset_id = ?", (asset_id,))
            conn.commit()
        self.append_history(
            kind,
            asset_id,
            action="delete",
            payload=payload or {"asset_id": asset_id},
            operator_id=operator_id,
            trace_id=trace_id,
            created_at=now,
        )

    def list_current(self, kind: str) -> list[dict[str, Any]]:
        current_table, _, _ = self.table_names(kind)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT asset_id, display_name, status, payload_json, created_at, updated_at, deleted_at
                FROM {current_table}
                ORDER BY created_at ASC, asset_id ASC
                """
            ).fetchall()
        return [self._decode_current(row) for row in rows]

    def get_current(self, kind: str, asset_id: str) -> dict[str, Any] | None:
        current_table, _, _ = self.table_names(kind)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT asset_id, display_name, status, payload_json, created_at, updated_at, deleted_at
                FROM {current_table}
                WHERE asset_id = ?
                """,
                (asset_id,),
            ).fetchone()
        return self._decode_current(row) if row else None

    @staticmethod
    def _decode_current(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "asset_id": row["asset_id"],
            "display_name": row["display_name"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "deleted_at": row["deleted_at"],
        }

    def append_history(
        self,
        kind: str,
        asset_id: str,
        *,
        action: str,
        payload: dict[str, Any],
        operator_id: str | None = None,
        trace_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        _, history_table, _ = self.table_names(kind)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {history_table} (
                    event_id, asset_id, action, payload_json, operator_id, trace_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    asset_id,
                    action,
                    json.dumps(_redact(payload), ensure_ascii=False, sort_keys=True),
                    operator_id,
                    trace_id,
                    created_at or _utc_now(),
                ),
            )
            conn.commit()

    def list_history(self, kind: str, asset_id: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        _, history_table, _ = self.table_names(kind)
        sql = (
            f"SELECT * FROM {history_table} "
            + ("WHERE asset_id = ? " if asset_id else "")
            + "ORDER BY created_at DESC LIMIT ?"
        )
        params: tuple[Any, ...] = (asset_id, limit) if asset_id else (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "asset_id": row["asset_id"],
                "action": row["action"],
                "payload": json.loads(row["payload_json"] or "{}"),
                "operator_id": row["operator_id"],
                "trace_id": row["trace_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def append_runtime_log(
        self,
        kind: str,
        asset_id: str,
        *,
        status: str,
        capability_name: str | None = None,
        invocation_type: str | None = None,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        error_message: str | None = None,
        trace_id: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        _, _, runtime_table = self.table_names(kind)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {runtime_table} (
                    log_id, asset_id, capability_name, invocation_type, status,
                    request_json, response_json, error_message, trace_id,
                    started_at, finished_at, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    asset_id,
                    capability_name,
                    invocation_type,
                    status,
                    json.dumps(_redact(request or {}), ensure_ascii=False, sort_keys=True),
                    json.dumps(_redact(response), ensure_ascii=False, sort_keys=True) if response is not None else None,
                    error_message,
                    trace_id,
                    started_at or _utc_now(),
                    finished_at,
                    duration_ms,
                ),
            )
            conn.commit()

    def list_runtime_logs(self, kind: str, asset_id: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        _, _, runtime_table = self.table_names(kind)
        sql = (
            f"SELECT * FROM {runtime_table} "
            + ("WHERE asset_id = ? " if asset_id else "")
            + "ORDER BY started_at DESC LIMIT ?"
        )
        params: tuple[Any, ...] = (asset_id, limit) if asset_id else (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "log_id": row["log_id"],
                "asset_id": row["asset_id"],
                "capability_name": row["capability_name"],
                "invocation_type": row["invocation_type"],
                "status": row["status"],
                "request": json.loads(row["request_json"] or "{}"),
                "response": json.loads(row["response_json"]) if row["response_json"] else None,
                "error_message": row["error_message"],
                "trace_id": row["trace_id"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "duration_ms": row["duration_ms"],
            }
            for row in rows
        ]
