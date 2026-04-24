from __future__ import annotations
import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

class AgentStorage:
    """Independent storage DAO for external Agent assets."""
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

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
                    latency_ms REAL,
                    success_rate REAL,
                    last_ping_at TEXT,
                    last_seen_at TEXT,
                    registered_at TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

    def upsert_agent(self, asset_dict: Dict[str, Any]):
        with self._lock, self._conn:
            now = datetime.now(timezone.utc).isoformat()
            keys = [
                "agent_id", "name", "agent_name", "version", "function_description",
                "endpoint", "auth_token", "role_tag", "trust_level", "status",
                "scope_json", "capabilities_json", "latency_ms", "success_rate",
                "last_ping_at", "last_seen_at", "registered_at", "created_at", "updated_at"
            ]
            
            data = {k: asset_dict.get(k) for k in keys}
            data["scope_json"] = json.dumps(asset_dict.get("scope", []))
            data["capabilities_json"] = json.dumps(asset_dict.get("capabilities", []))
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
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
