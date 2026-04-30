from __future__ import annotations
import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

class AgentStorage:
    """Independent storage DAO for external Agent assets."""
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        """Close the owned SQLite connection once."""
        with self._lock:
            conn = getattr(self, "_conn", None)
            if conn is None:
                return
            try:
                conn.close()
            finally:
                self._conn = None

    def _init_db(self):
        with self._lock, self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    agent_name TEXT,
                    version TEXT,
                    function_description TEXT,
                    endpoint TEXT,
                    auth_token TEXT,
                    role_tag TEXT,
                    trust_level TEXT,
                    status TEXT,
                    scope_json TEXT,
                    capabilities_json TEXT,
                    adapter_type TEXT,
                    adapter_config_json TEXT,
                    auth_config_json TEXT,
                    service_hooks_json TEXT,
                    protocol_capabilities_json TEXT,
                    latency_ms REAL,
                    success_rate REAL,
                    last_ping_at TEXT,
                    last_seen_at TEXT,
                    registered_at TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            existing_columns = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(agents)").fetchall()
            }
            for column, ddl in {
                "adapter_type": "ALTER TABLE agents ADD COLUMN adapter_type TEXT",
                "adapter_config_json": "ALTER TABLE agents ADD COLUMN adapter_config_json TEXT",
                "auth_config_json": "ALTER TABLE agents ADD COLUMN auth_config_json TEXT",
                "service_hooks_json": "ALTER TABLE agents ADD COLUMN service_hooks_json TEXT",
                "protocol_capabilities_json": "ALTER TABLE agents ADD COLUMN protocol_capabilities_json TEXT",
            }.items():
                if column not in existing_columns:
                    self._conn.execute(ddl)

    def upsert_agent(self, asset_dict: Dict[str, Any]):
        with self._lock, self._conn:
            now = datetime.now(timezone.utc).isoformat()
            keys = [
                "agent_id", "name", "agent_name", "version", "function_description",
                "endpoint", "auth_token", "role_tag", "trust_level", "status",
                "scope_json", "capabilities_json", "adapter_type", "adapter_config_json",
                "auth_config_json", "service_hooks_json", "protocol_capabilities_json",
                "latency_ms", "success_rate",
                "last_ping_at", "last_seen_at", "registered_at", "created_at", "updated_at"
            ]
            
            data = {k: asset_dict.get(k) for k in keys}
            data["scope_json"] = json.dumps(asset_dict.get("scope", []))
            data["capabilities_json"] = json.dumps(asset_dict.get("capabilities", []))
            data["adapter_config_json"] = json.dumps(asset_dict.get("adapter_config", {}))
            data["auth_config_json"] = json.dumps(asset_dict.get("auth_config", {}))
            data["service_hooks_json"] = json.dumps(asset_dict.get("service_hooks", []))
            data["protocol_capabilities_json"] = json.dumps(asset_dict.get("protocol_capabilities", []))
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
                d["adapter_config"] = json.loads(d.pop("adapter_config_json", None) or "{}")
                d["auth_config"] = json.loads(d.pop("auth_config_json", None) or "{}")
                d["service_hooks"] = json.loads(d.pop("service_hooks_json", None) or "[]")
                d["protocol_capabilities"] = json.loads(d.pop("protocol_capabilities_json", None) or "[]")
                records.append(d)
            return records

    def delete_agent(self, agent_id: str):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
