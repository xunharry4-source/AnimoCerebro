from __future__ import annotations

import sqlite3
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
import enum

logger = logging.getLogger(__name__)

class AssetDatabaseStore:
    """
    Persistent registry for system assets: Agents, MCP Servers, CLI Tools, and Plugins.
    Uses SQLite for robust, single-source-of-truth management.
    """

    def _json_serial(self, obj):
        """Standard JSON serializer for Zentex objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if hasattr(obj, "value"): # Enum
            return obj.value
        return str(obj)

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            
            # 1. Core Tasks Table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    parent_task_id TEXT,
                    status TEXT,
                    task_type TEXT,
                    priority TEXT,
                    title TEXT,
                    full_data_json TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            # 2. Task Idempotency Table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS task_idempotency (
                    idempotency_key TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    created_at TEXT
                )
            """)

            # 3. Task Interventions Table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS task_interventions (
                    idempotency_key TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    action TEXT,
                    data_json TEXT,
                    created_at TEXT
                )
            """)

            # 4. Task Suspensions Table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS task_suspensions (
                    task_id TEXT PRIMARY KEY,
                    data_json TEXT,
                    updated_at TEXT
                )
            """)
            
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_task_parent ON tasks(parent_task_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_task_status_col ON tasks(status)")

    # --- Task Operations ---

    def upsert_task(self, task_dict: Dict[str, Any]):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute("""
                    INSERT OR REPLACE INTO tasks 
                    (task_id, parent_task_id, status, task_type, priority, title, full_data_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_dict.get("task_id"),
                    task_dict.get("parent_task_id"),
                    str(task_dict.get("status")),
                    str(task_dict.get("task_type")),
                    str(task_dict.get("priority")),
                    task_dict.get("title"),
                    json.dumps(task_dict, default=self._json_serial),
                    task_dict.get("created_at"),
                    now
                ))

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM tasks")
            records = []
            for row in cursor:
                d = json.loads(row["full_data_json"])
                records.append(d)
            return records

    def delete_task(self, task_id: str):
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
                self._conn.execute("DELETE FROM task_suspensions WHERE task_id = ?", (task_id,))

    def upsert_idempotency(self, key: str, task_id: str):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute("INSERT OR REPLACE INTO task_idempotency (idempotency_key, task_id, created_at) VALUES (?, ?, ?)", (key, task_id, now))

    def get_task_by_idempotency(self, key: str) -> Optional[str]:
        with self._lock:
            cursor = self._conn.execute("SELECT task_id FROM task_idempotency WHERE idempotency_key = ?", (key,))
            row = cursor.fetchone()
            return row["task_id"] if row else None

    def list_idempotency(self) -> Dict[str, str]:
        with self._lock:
            cursor = self._conn.execute("SELECT idempotency_key, task_id FROM task_idempotency")
            return {row["idempotency_key"]: row["task_id"] for row in cursor}

    def upsert_intervention(self, key: str, task_id: str, action: str, data: Dict[str, Any]):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute("INSERT OR REPLACE INTO task_interventions (idempotency_key, task_id, action, data_json, created_at) VALUES (?, ?, ?, ?, ?)", (
                    key, task_id, action, json.dumps(data, default=self._json_serial), now
                ))

    def list_interventions(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT idempotency_key, data_json FROM task_interventions")
            return {row["idempotency_key"]: json.loads(row["data_json"]) for row in cursor}

    def upsert_task_suspension(self, task_id: str, data: Dict[str, Any]):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute("INSERT OR REPLACE INTO task_suspensions (task_id, data_json, updated_at) VALUES (?, ?, ?)", (
                    task_id, json.dumps(data, default=self._json_serial), now
                ))

    def delete_task_suspension(self, task_id: str):
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM task_suspensions WHERE task_id = ?", (task_id,))

    def list_task_suspensions(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT task_id, data_json FROM task_suspensions")
            return {row["task_id"]: json.loads(row["data_json"]) for row in cursor}

    # --- Agent Operations ---

    def upsert_agent(self, asset_dict: Dict[str, Any]):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                keys = [
                    "agent_id", "name", "agent_name", "version", "function_description",
                    "endpoint", "auth_token", "role_tag", "trust_level", "status",
                    "scope_json", "capabilities_json", "latency_ms", "success_rate",
                    "last_ping_at", "last_seen_at", "registered_at", "created_at", "updated_at"
                ]
                
                # Mapping helper to handle JSON fields
                data = {k: asset_dict.get(k) for k in keys}
                data["scope_json"] = json.dumps(asset_dict.get("scope", []), default=self._json_serial)
                data["capabilities_json"] = json.dumps(asset_dict.get("capabilities", []), default=self._json_serial)
                data["updated_at"] = now
                
                placeholders = ", ".join(["?"] * len(keys))
                columns = ", ".join(keys)
                sql = f"INSERT OR REPLACE INTO agents ({columns}) VALUES ({placeholders})"
                self._conn.execute(sql, [data[k] for k in keys])

    def list_agents(self) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM agents")
            records = []
            for row in cursor:
                d = dict(row)
                d["scope"] = json.loads(d.pop("scope_json") or "[]")
                d["capabilities"] = json.loads(d.pop("capabilities_json") or "[]")
                records.append(d)
            return records

    def delete_agent(self, agent_id: str):
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))

    # --- MCP Operations ---

    def upsert_mcp_server(self, server_id: str, config_dict: Dict[str, Any], status: str, tool_count: int = 0, error: str = None):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute("""
                    INSERT OR REPLACE INTO mcp_servers 
                    (server_id, transport_type, command, args_json, env_json, tool_bindings_json, status, tool_count, error_message, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    server_id,
                    config_dict.get("transport_type"),
                    config_dict.get("command"),
                    json.dumps(config_dict.get("args", []), default=self._json_serial),
                    json.dumps(config_dict.get("env", {}), default=self._json_serial),
                    json.dumps(config_dict.get("tool_bindings", []), default=self._json_serial),
                    status,
                    tool_count,
                    error,
                    now
                ))

    def list_mcp_servers(self) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM mcp_servers")
            return [dict(row) for row in cursor]

    # --- CLI Operations ---

    def upsert_cli_tool(self, tool_id: str, config_dict: Dict[str, Any], status: str):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                self._conn.execute("""
                    INSERT OR REPLACE INTO cli_tools 
                    (tool_id, command_executable, command_args_json, env_json, project_path, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    tool_id,
                    config_dict.get("command_executable"),
                    json.dumps(config_dict.get("command_args", []), default=self._json_serial),
                    json.dumps(config_dict.get("env", {}), default=self._json_serial),
                    config_dict.get("project_path"),
                    status,
                    now
                ))

    def list_cli_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM cli_tools")
            return [dict(row) for row in cursor]

    # --- Plugin Operations ---

    def upsert_plugin(self, category: Literal["cognitive", "functional"], plugin_id: str, spec_dict: Dict[str, Any], registration_dict: Dict[str, Any]):
        with self._lock:
            with self._conn:
                now = datetime.now(timezone.utc).isoformat()
                status = spec_dict.get("status")
                if hasattr(status, "value"): status = status.value
                
                self._conn.execute("""
                    INSERT OR REPLACE INTO system_plugins 
                    (plugin_id, category, behavior_key, version, status, spec_json, source_kind, usage_count, failure_count, created_at, updated_at, started_at, stopped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    plugin_id,
                    category,
                    spec_dict.get("behavior_key"),
                    spec_dict.get("version"),
                    str(status),
                    json.dumps(spec_dict, default=self._json_serial),
                    registration_dict.get("source_kind"),
                    registration_dict.get("usage_count", 0),
                    registration_dict.get("failure_count", 0),
                    registration_dict.get("created_at"),
                    now,
                    registration_dict.get("started_at"),
                    registration_dict.get("stopped_at")
                ))

    def list_plugins(self, category: Optional[Literal["cognitive", "functional"]] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if category:
                cursor = self._conn.execute("SELECT * FROM system_plugins WHERE category = ?", (category,))
            else:
                cursor = self._conn.execute("SELECT * FROM system_plugins")
            return [dict(row) for row in cursor]

    def get_plugin(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM system_plugins WHERE plugin_id = ?", (plugin_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_plugin(self, plugin_id: str):
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM system_plugins WHERE plugin_id = ?", (plugin_id,))

    def close(self):
        self._conn.close()
