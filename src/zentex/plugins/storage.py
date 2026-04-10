from __future__ import annotations
import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

class PluginStorage:
    """Independent storage DAO for system-level native plugins."""
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._lock, self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS system_plugins (
                    plugin_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    behavior_key TEXT,
                    version TEXT,
                    status TEXT,
                    spec_json TEXT,
                    source_kind TEXT,
                    usage_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    started_at TEXT,
                    stopped_at TEXT
                )
            """)
            
            # Plugin relationships table (cognitive -> functional bindings)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS plugin_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cognitive_plugin_id TEXT NOT NULL,
                    functional_plugin_id TEXT NOT NULL,
                    role TEXT DEFAULT 'primary',
                    priority INTEGER DEFAULT 1,
                    fallback_id TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (cognitive_plugin_id) REFERENCES system_plugins(plugin_id),
                    FOREIGN KEY (functional_plugin_id) REFERENCES system_plugins(plugin_id),
                    UNIQUE(cognitive_plugin_id, functional_plugin_id)
                )
            """)
            
            # Index for fast lookups
            try:
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_cognitive_plugin ON plugin_relations(cognitive_plugin_id)")
                self._conn.execute("CREATE INDEX IF NOT EXISTS idx_functional_plugin ON plugin_relations(functional_plugin_id)")
            except sqlite3.OperationalError:
                pass  # Indices may already exist

    def upsert_plugin(self, category: Literal["cognitive", "functional"], plugin_id: str, spec_dict: Dict[str, Any], registration_dict: Dict[str, Any]):
        with self._lock, self._conn:
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
                json.dumps(spec_dict),
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
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM system_plugins WHERE plugin_id = ?", (plugin_id,))
    
    # ==================== Plugin Relations Methods ====================
    
    def create_relation(
        self,
        cognitive_plugin_id: str,
        functional_plugin_id: str,
        role: str = "primary",
        priority: int = 1,
        fallback_id: Optional[str] = None,
    ) -> None:
        """Create a cognitive←→functional plugin relationship."""
        with self._lock, self._conn:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute("""
                INSERT OR REPLACE INTO plugin_relations
                (cognitive_plugin_id, functional_plugin_id, role, priority, fallback_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cognitive_plugin_id, functional_plugin_id, role, priority, fallback_id, now, now))
    
    def delete_relation(self, cognitive_plugin_id: str, functional_plugin_id: str) -> None:
        """Delete a cognitive←→functional plugin relationship."""
        with self._lock, self._conn:
            self._conn.execute("""
                DELETE FROM plugin_relations
                WHERE cognitive_plugin_id = ? AND functional_plugin_id = ?
            """, (cognitive_plugin_id, functional_plugin_id))
    
    def query_relations_by_cognitive(self, cognitive_plugin_id: str) -> List[Dict[str, Any]]:
        """Query all functional plugins bound to a cognitive plugin."""
        with self._lock:
            cursor = self._conn.execute("""
                SELECT * FROM plugin_relations WHERE cognitive_plugin_id = ? ORDER BY priority
            """, (cognitive_plugin_id,))
            return [dict(row) for row in cursor]
    
    def query_relations_by_functional(self, functional_plugin_id: str) -> List[Dict[str, Any]]:
        """Query all cognitive plugins that use a functional plugin."""
        with self._lock:
            cursor = self._conn.execute("""
                SELECT * FROM plugin_relations WHERE functional_plugin_id = ? ORDER BY priority
            """, (functional_plugin_id,))
            return [dict(row) for row in cursor]
    
    def get_relation(self, cognitive_plugin_id: str, functional_plugin_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific cognitive←→functional plugin relationship."""
        with self._lock:
            cursor = self._conn.execute("""
                SELECT * FROM plugin_relations
                WHERE cognitive_plugin_id = ? AND functional_plugin_id = ?
            """, (cognitive_plugin_id, functional_plugin_id))
            row = cursor.fetchone()
            return dict(row) if row else None
