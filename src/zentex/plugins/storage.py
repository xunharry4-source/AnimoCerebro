from __future__ import annotations
import logging
import sqlite3
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal, Union

from zentex.plugins.plugin_ids import canonicalize_plugin_id

logger = logging.getLogger(__name__)

class PluginStorage:
    """Independent storage DAO for system-level native plugins."""
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
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
                CREATE TABLE IF NOT EXISTS system_plugins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_id TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    behavior_key TEXT,
                    version TEXT,
                    lifecycle_status TEXT,
                    operational_status TEXT,
                    spec_json TEXT,
                    source_kind TEXT,
                    usage_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    started_at TEXT,
                    stopped_at TEXT,
                    plugin_category TEXT,
                    plugin_url TEXT,
                    description TEXT
                )
            """)
            self._ensure_system_plugin_columns()
            
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
            except sqlite3.OperationalError as exc:
                if "already exists" in str(exc).lower():
                    logger.info("plugin_relations indices already exist; skipping duplicate creation")
                else:
                    # Standard redline: never swallow plugin storage migration failures
                    # and pretend the schema is healthy. Keep traceback.
                    logger.exception("Failed to initialize plugin_relations indices")
                    raise

    def _ensure_system_plugin_columns(self) -> None:
        cursor = self._conn.execute("PRAGMA table_info(system_plugins)")
        columns = {str(row[1]) for row in cursor.fetchall()}
        
        # 添加 id 字段（如果不存在）
        if "id" not in columns:
            # SQLite 不支持直接添加 AUTOINCREMENT 列，需要重建表
            try:
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_plugins_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        plugin_id TEXT UNIQUE NOT NULL,
                        category TEXT NOT NULL,
                        behavior_key TEXT,
                        version TEXT,
                        lifecycle_status TEXT,
                        operational_status TEXT,
                        spec_json TEXT,
                        source_kind TEXT,
                        usage_count INTEGER DEFAULT 0,
                        failure_count INTEGER DEFAULT 0,
                        created_at TEXT,
                        updated_at TEXT,
                        started_at TEXT,
                        stopped_at TEXT,
                        plugin_category TEXT,
                        plugin_url TEXT,
                        description TEXT
                    )
                """)
                # 复制数据
                self._conn.execute("""
                    INSERT INTO system_plugins_new 
                    (plugin_id, category, behavior_key, version, lifecycle_status, operational_status, 
                     spec_json, source_kind, usage_count, failure_count, created_at, updated_at, 
                     started_at, stopped_at, plugin_category, plugin_url, description)
                    SELECT plugin_id, category, behavior_key, version, lifecycle_status, operational_status,
                           spec_json, source_kind, usage_count, failure_count, created_at, updated_at,
                           started_at, stopped_at, plugin_category, plugin_url, description
                    FROM system_plugins
                """)
                # 删除旧表
                self._conn.execute("DROP TABLE system_plugins")
                # 重命名新表
                self._conn.execute("ALTER TABLE system_plugins_new RENAME TO system_plugins")
            except Exception as e:
                # 如果迁移失败，忽略错误（可能是新数据库）
                pass
        
        if "lifecycle_status" not in columns:
            self._conn.execute("ALTER TABLE system_plugins ADD COLUMN lifecycle_status TEXT")
        if "operational_status" not in columns:
            self._conn.execute("ALTER TABLE system_plugins ADD COLUMN operational_status TEXT")
        if "plugin_category" not in columns:
            self._conn.execute("ALTER TABLE system_plugins ADD COLUMN plugin_category TEXT")
        if "plugin_url" not in columns:
            self._conn.execute("ALTER TABLE system_plugins ADD COLUMN plugin_url TEXT")
        if "description" not in columns:
            self._conn.execute("ALTER TABLE system_plugins ADD COLUMN description TEXT")

    @staticmethod
    def _normalize_lifecycle_status(value: Any) -> str:
        return str(getattr(value, "value", value) or "").strip().lower()

    @classmethod
    def _derive_operational_status(
        cls,
        *,
        lifecycle_status: str,
        registration_dict: Dict[str, Any],
        spec_dict: Dict[str, Any],
    ) -> str:
        logger.warning(f"[DEBUG] _derive_operational_status input: lifecycle={lifecycle_status}, registration_stopped_at={registration_dict.get('stopped_at')}")
        explicit = str(registration_dict.get("operational_status") or "").strip().lower()
        if explicit in {"enabled", "stopped", "abnormal"}:
            return explicit
        health = registration_dict.get("health_status", spec_dict.get("health_status"))
        normalized_health = str(getattr(health, "value", health) or "").strip().lower()
        if normalized_health in {"degraded", "unhealthy", "abnormal"}:
            return "abnormal"
        if registration_dict.get("stopped_at"):
            logger.warning(f"[DEBUG] _derive_operational_status returning stopped because stopped_at={registration_dict.get('stopped_at')}")
            return "stopped"
        if lifecycle_status != "active":
            return "unavailable"
        logger.warning(f"[DEBUG] _derive_operational_status returning enabled")
        return "enabled"

    def upsert_plugin(self, category: Literal["cognitive", "functional"], plugin_id: str, spec_dict: Dict[str, Any], registration_dict: Dict[str, Any]):
        plugin_id = canonicalize_plugin_id(plugin_id)
        spec_dict = dict(spec_dict)
        spec_dict["plugin_id"] = plugin_id
        
        # 📝 审计日志：记录 upsert 操作
        logger.info(
            f"[PluginStorage.Upsert] plugin_id={plugin_id}, category={category}, "
            f"lifecycle_status={spec_dict.get('lifecycle_status')}, "
            f"operational_status={spec_dict.get('operational_status')}"
        )
        
        with self._lock, self._conn:
            now = datetime.now(timezone.utc).isoformat()
            lifecycle_val = self._normalize_lifecycle_status(
                registration_dict.get("lifecycle_status")
                or spec_dict.get("lifecycle_status")
            )
            if not lifecycle_val:
                lifecycle_val = "candidate"
            lifecycle_status = lifecycle_val
            operational_status = self._derive_operational_status(
                lifecycle_status=lifecycle_status,
                registration_dict=registration_dict,
                spec_dict=spec_dict,
            )
            spec_dict["lifecycle_status"] = lifecycle_status
            spec_dict["operational_status"] = operational_status
            
            # 检查是否已存在
            existing = self.get_plugin(plugin_id)
            if existing:
                logger.debug(
                    f"[PluginStorage.Upsert] Plugin exists (ID={existing.get('id')}), will UPDATE"
                )
            else:
                logger.debug(
                    f"[PluginStorage.Upsert] Plugin does not exist, will INSERT"
                )
            
            self._conn.execute("""
                INSERT INTO system_plugins 
                (plugin_id, category, behavior_key, version, lifecycle_status, operational_status, spec_json, source_kind, usage_count, failure_count, created_at, updated_at, started_at, stopped_at, plugin_category, plugin_url, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plugin_id) DO UPDATE SET
                    category=excluded.category,
                    behavior_key=excluded.behavior_key,
                    version=excluded.version,
                    lifecycle_status=excluded.lifecycle_status,
                    operational_status=excluded.operational_status,
                    spec_json=excluded.spec_json,
                    source_kind=excluded.source_kind,
                    usage_count=excluded.usage_count,
                    failure_count=excluded.failure_count,
                    updated_at=excluded.updated_at,
                    started_at=excluded.started_at,
                    stopped_at=excluded.stopped_at,
                    plugin_category=excluded.plugin_category,
                    plugin_url=excluded.plugin_url,
                    description=excluded.description
            """, (
                plugin_id,
                category,
                spec_dict.get("behavior_key"),
                spec_dict.get("version"),
                lifecycle_status,
                operational_status,
                json.dumps(spec_dict),
                registration_dict.get("source_kind"),
                registration_dict.get("usage_count", 0),
                registration_dict.get("failure_count", 0),
                registration_dict.get("created_at"),
                now,
                registration_dict.get("started_at"),
                registration_dict.get("stopped_at"),
                spec_dict.get("plugin_category"),
                spec_dict.get("plugin_url"),
                spec_dict.get("description") or registration_dict.get("description")
            ))
            
            # 📝 审计日志：确认操作结果
            result = self.get_plugin(plugin_id)
            if result:
                logger.info(
                    f"[PluginStorage.Upsert] SUCCESS: plugin_id={plugin_id}, ID={result.get('id')}, "
                    f"action={'UPDATE' if existing else 'INSERT'}"
                )
            else:
                logger.error(f"[PluginStorage.Upsert] FAILED: plugin_id={plugin_id}")

    def list_plugins(self, category: Optional[Literal["cognitive", "functional"]] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if category:
                cursor = self._conn.execute("SELECT * FROM system_plugins WHERE category = ?", (category,))
            else:
                cursor = self._conn.execute("SELECT * FROM system_plugins")
            return [dict(row) for row in cursor]

    def get_plugin(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        plugin_id = canonicalize_plugin_id(plugin_id)
        with self._lock:
            cursor = self._conn.execute("SELECT * FROM system_plugins WHERE plugin_id = ?", (plugin_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_plugin(self, plugin_id: str, fields: Dict[str, Any]) -> None:
        plugin_id = canonicalize_plugin_id(plugin_id)
        current = self.get_plugin(plugin_id)
        if current is None:
            raise KeyError(f"Unknown plugin: {plugin_id}")

        merged = dict(current)
        merged.update(fields)
        lifecycle_status = self._normalize_lifecycle_status(merged.get("lifecycle_status")) or "candidate"
        operational_status = str(merged.get("operational_status") or "").strip().lower()
        if operational_status not in {"enabled", "stopped", "abnormal", "unavailable"}:
            operational_status = self._derive_operational_status(
                lifecycle_status=lifecycle_status,
                registration_dict=merged,
                spec_dict=json.loads(merged.get("spec_json") or "{}"),
            )

        spec_dict = json.loads(merged.get("spec_json") or "{}")
        spec_dict["plugin_id"] = plugin_id
        spec_dict["lifecycle_status"] = lifecycle_status
        spec_dict["operational_status"] = operational_status

        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE system_plugins
                SET category = ?,
                    behavior_key = ?,
                    version = ?,
                    lifecycle_status = ?,
                    operational_status = ?,
                    spec_json = ?,
                    source_kind = ?,
                    usage_count = ?,
                    failure_count = ?,
                    created_at = ?,
                    updated_at = ?,
                    started_at = ?,
                    stopped_at = ?
                WHERE plugin_id = ?
                """,
                (
                    merged.get("category"),
                    merged.get("behavior_key"),
                    merged.get("version"),
                    lifecycle_status,
                    operational_status,
                    json.dumps(spec_dict),
                    merged.get("source_kind"),
                    merged.get("usage_count", 0),
                    merged.get("failure_count", 0),
                    merged.get("created_at"),
                    merged.get("updated_at"),
                    merged.get("started_at"),
                    merged.get("stopped_at"),
                    plugin_id,
                ),
            )

    def delete_plugin(self, plugin_id: str):
        plugin_id = canonicalize_plugin_id(plugin_id)
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
        cognitive_plugin_id = canonicalize_plugin_id(cognitive_plugin_id)
        functional_plugin_id = canonicalize_plugin_id(functional_plugin_id)
        fallback_id = canonicalize_plugin_id(fallback_id) if fallback_id else None
        with self._lock, self._conn:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.execute("""
                INSERT OR REPLACE INTO plugin_relations
                (cognitive_plugin_id, functional_plugin_id, role, priority, fallback_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cognitive_plugin_id, functional_plugin_id, role, priority, fallback_id, now, now))
    
    def delete_relation(self, cognitive_plugin_id: str, functional_plugin_id: str) -> None:
        """Delete a cognitive←→functional plugin relationship."""
        cognitive_plugin_id = canonicalize_plugin_id(cognitive_plugin_id)
        functional_plugin_id = canonicalize_plugin_id(functional_plugin_id)
        with self._lock, self._conn:
            self._conn.execute("""
                DELETE FROM plugin_relations
                WHERE cognitive_plugin_id = ? AND functional_plugin_id = ?
            """, (cognitive_plugin_id, functional_plugin_id))
    
    def query_relations_by_cognitive(self, cognitive_plugin_id: str) -> List[Dict[str, Any]]:
        """Query all functional plugins bound to a cognitive plugin."""
        cognitive_plugin_id = canonicalize_plugin_id(cognitive_plugin_id)
        with self._lock:
            cursor = self._conn.execute("""
                SELECT * FROM plugin_relations WHERE cognitive_plugin_id = ? ORDER BY priority
            """, (cognitive_plugin_id,))
            return [dict(row) for row in cursor]
    
    def query_relations_by_functional(self, functional_plugin_id: str) -> List[Dict[str, Any]]:
        """Query all cognitive plugins that use a functional plugin."""
        functional_plugin_id = canonicalize_plugin_id(functional_plugin_id)
        with self._lock:
            cursor = self._conn.execute("""
                SELECT * FROM plugin_relations WHERE functional_plugin_id = ? ORDER BY priority
            """, (functional_plugin_id,))
            return [dict(row) for row in cursor]
    
    def get_relation(self, cognitive_plugin_id: str, functional_plugin_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific cognitive←→functional plugin relationship."""
        cognitive_plugin_id = canonicalize_plugin_id(cognitive_plugin_id)
        functional_plugin_id = canonicalize_plugin_id(functional_plugin_id)
        with self._lock:
            cursor = self._conn.execute("""
                SELECT * FROM plugin_relations
                WHERE cognitive_plugin_id = ? AND functional_plugin_id = ?
            """, (cognitive_plugin_id, functional_plugin_id))
            row = cursor.fetchone()
            return dict(row) if row else None
