from __future__ import annotations
import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

class CliStorage:
    """Independent storage DAO for CLI tool assets."""
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._lock, self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS cli_tools (
                    tool_id TEXT PRIMARY KEY,
                    command_executable TEXT,
                    command_args_json TEXT,
                    env_json TEXT,
                    project_path TEXT,
                    status TEXT,
                    last_execution_at TEXT,
                    updated_at TEXT
                )
            """)

    def upsert_cli_tool(self, tool_id: str, config_dict: Dict[str, Any], status: str):
        with self._lock, self._conn:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute("""
                INSERT OR REPLACE INTO cli_tools 
                (tool_id, command_executable, command_args_json, env_json, project_path, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tool_id,
                config_dict.get("command_executable"),
                json.dumps(config_dict.get("command_args", [])),
                json.dumps(config_dict.get("env", {})),
                config_dict.get("project_path"),
                status,
                now
            ))

    def list_cli_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM cli_tools")
            return [dict(row) for row in cursor]

    def delete_cli_tool(self, tool_id: str):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM cli_tools WHERE tool_id = ?", (tool_id,))
