from __future__ import annotations
import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

class McpStorage:
    """Independent storage DAO for MCP server assets."""
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_servers (
                    server_id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    version TEXT,
                    tags_json TEXT,
                    owner TEXT,
                    transport_type TEXT,
                    command TEXT,
                    args_json TEXT,
                    env_json TEXT,
                    tool_bindings_json TEXT,
                    status TEXT,
                    tool_count INTEGER,
                    error_message TEXT,
                    last_health_check_at TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_execution_records (
                    record_id TEXT PRIMARY KEY,
                    server_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    duration_ms REAL,
                    error TEXT,
                    payload_json TEXT,
                    result_json TEXT,
                    trace_id TEXT
                )
            """)

    def upsert_mcp_server(self, server_id: str, config_dict: Dict[str, Any], status: str, tool_count: int = 0, error: str = None):
        with self._lock, self._conn:
            now = datetime.now(timezone.utc).isoformat()
            # Check if server exists to preserve created_at
            existing = self._conn.execute("SELECT created_at FROM mcp_servers WHERE server_id = ?", (server_id,)).fetchone()
            created_at = existing["created_at"] if existing else now
            
            self._conn.execute("""
                INSERT OR REPLACE INTO mcp_servers 
                (server_id, name, description, version, tags_json, owner, transport_type, command, args_json, env_json, tool_bindings_json, status, tool_count, error_message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                server_id,
                config_dict.get("name"),
                config_dict.get("description"),
                config_dict.get("version"),
                json.dumps(config_dict.get("tags", [])),
                config_dict.get("owner"),
                config_dict.get("transport_type"),
                config_dict.get("command"),
                json.dumps(config_dict.get("args", [])),
                json.dumps(config_dict.get("env", {})),
                json.dumps(config_dict.get("tool_bindings", [])),
                status,
                tool_count,
                error,
                created_at,
                now
            ))

    def list_mcp_servers(self) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM mcp_servers")
            return [dict(row) for row in cursor]

    def delete_mcp_server(self, server_id: str):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM mcp_servers WHERE server_id = ?", (server_id,))

    def add_execution_record(self, record_id: str, server_id: str, tool_name: str, status: str, start_time: datetime, end_time: Optional[datetime], payload: Dict[str, Any], result: Optional[Dict[str, Any]], error: Optional[str] = None, trace_id: Optional[str] = None):
        with self._lock, self._conn:
            duration = None
            if end_time:
                duration = (end_time - start_time).total_seconds() * 1000
            
            self._conn.execute("""
                INSERT INTO mcp_execution_records 
                (record_id, server_id, tool_name, status, start_time, end_time, duration_ms, error, payload_json, result_json, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id, server_id, tool_name, status, 
                start_time.isoformat(), 
                end_time.isoformat() if end_time else None,
                duration, error, 
                json.dumps(payload), 
                json.dumps(result) if result else None,
                trace_id
            ))

    def list_execution_records(self, server_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            if server_id:
                cursor = self._conn.execute("SELECT * FROM mcp_execution_records WHERE server_id = ? ORDER BY start_time DESC LIMIT ?", (server_id, limit))
            else:
                cursor = self._conn.execute("SELECT * FROM mcp_execution_records ORDER BY start_time DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor]
