from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from zentex.common.storage_paths import get_storage_paths


class ModuleLogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    log_id: str
    timestamp: str
    source_module: str
    object_id: str
    object_label: str
    action: str
    action_label: str
    status: str
    content: str
    source: str
    operator_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ModuleLogPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ModuleLogItem] = Field(default_factory=list)
    page: int
    page_size: int
    total_items: int
    total_pages: int


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_module_log_content(
    *,
    module_label: str,
    object_label: str,
    action_label: str,
    before_status: str | None = None,
    after_status: str | None = None,
    reason: str | None = None,
    extra: str | None = None,
) -> str:
    parts = [f"{module_label}「{object_label}」{action_label}"]
    before = _compact(before_status)
    after = _compact(after_status)
    if before or after:
        parts.append(f"状态变化：{before or '-'} -> {after or '-'}")
    if reason:
        parts.append(f"原因：{reason}")
    if extra:
        parts.append(extra)
    return "。".join(parts) + "。"


class ModuleLogService:
    def __init__(self, root_path: str | Path | None = None) -> None:
        if root_path is None:
            root_path = get_storage_paths().runtime_data_dir / "module_logs"
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def close(self) -> None:
        return None

    def record_log(
        self,
        *,
        source_module: str,
        module_label: str,
        action: str,
        action_label: str,
        object_id: str,
        object_label: str | None = None,
        before_status: str | None = None,
        after_status: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
        operator_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> str:
        display_label = object_label or object_id
        content = build_module_log_content(
            module_label=module_label,
            object_label=display_label,
            action_label=action_label,
            before_status=before_status,
            after_status=after_status,
            reason=reason,
        )
        event_status = status or after_status or "completed"
        log_id = f"module-log:{source_module}:{action}:{uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = {
            "before_status": before_status,
            "after_status": after_status,
            "reason": reason,
            "details": details or {},
        }
        db_path = self._db_path_for(source_module)
        with self._lock:
            conn = self._connect(db_path)
            try:
                self._ensure_schema(conn)
                conn.execute(
                    """
                    INSERT INTO module_logs (
                        log_id, timestamp, source_module, object_id, object_label,
                        action, action_label, status, content, source, operator_id, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log_id,
                        timestamp,
                        source_module,
                        object_id,
                        display_label,
                        action,
                        action_label,
                        event_status,
                        content,
                        source or f"zentex.{source_module}.logs",
                        operator_id or "system",
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return log_id

    def query_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 40,
        source_module: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> ModuleLogPage:
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        if source_module:
            return self._query_one_module(
                source_module=source_module,
                page=page,
                page_size=page_size,
                status=status,
                search=search,
            )
        return self._query_all_modules(page=page, page_size=page_size, status=status, search=search)

    def _query_one_module(
        self,
        *,
        source_module: str,
        page: int,
        page_size: int,
        status: Optional[str],
        search: Optional[str],
    ) -> ModuleLogPage:
        where: list[str] = ["source_module = ?"]
        params: list[Any] = [source_module]
        if status:
            where.append("status = ?")
            params.append(status)
        if search:
            like = f"%{search}%"
            where.append(
                """(
                    log_id LIKE ? OR object_id LIKE ? OR object_label LIKE ?
                    OR action LIKE ? OR action_label LIKE ? OR status LIKE ?
                    OR content LIKE ? OR source LIKE ? OR operator_id LIKE ?
                    OR details_json LIKE ?
                )"""
            )
            params.extend([like] * 10)
        where_clause = f"WHERE {' AND '.join(where)}"
        db_path = self._db_path_for(source_module)
        if not db_path.exists():
            return ModuleLogPage(items=[], page=page, page_size=page_size, total_items=0, total_pages=0)
        with self._lock:
            conn = self._connect(db_path)
            try:
                self._ensure_schema(conn)
                total = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS count FROM module_logs {where_clause}",
                        params,
                    ).fetchone()["count"]
                )
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM module_logs
                    {where_clause}
                    ORDER BY timestamp DESC, log_id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (*params, page_size, (page - 1) * page_size),
                ).fetchall()
            finally:
                conn.close()
        return self._page_from_rows(rows, page=page, page_size=page_size, total=total)

    def _query_all_modules(
        self,
        *,
        page: int,
        page_size: int,
        status: Optional[str],
        search: Optional[str],
    ) -> ModuleLogPage:
        all_items: list[ModuleLogItem] = []
        total = 0
        per_module_limit = (page - 1) * page_size + page_size
        for db_path in sorted(self.root_path.glob("*_logs.sqlite3")):
            source_module = db_path.name.removesuffix("_logs.sqlite3")
            page_payload = self._query_one_module(
                source_module=source_module,
                page=1,
                page_size=per_module_limit,
                status=status,
                search=search,
            )
            total += page_payload.total_items
            all_items.extend(page_payload.items)
        all_items.sort(key=lambda item: (item.timestamp, item.log_id), reverse=True)
        start = (page - 1) * page_size
        end = start + page_size
        return ModuleLogPage(
            items=all_items[start:end],
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    def _page_from_rows(self, rows: list[sqlite3.Row], *, page: int, page_size: int, total: int) -> ModuleLogPage:
        items = []
        for row in rows:
            details = json.loads(row["details_json"] or "{}")
            items.append(
                ModuleLogItem(
                    log_id=row["log_id"],
                    timestamp=row["timestamp"],
                    source_module=row["source_module"],
                    object_id=row["object_id"],
                    object_label=row["object_label"],
                    action=row["action"],
                    action_label=row["action_label"],
                    status=row["status"],
                    content=row["content"],
                    source=row["source"],
                    operator_id=row["operator_id"],
                    details=details,
                )
            )
        return ModuleLogPage(
            items=items,
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )

    def _db_path_for(self, source_module: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in source_module.strip())
        if not safe:
            safe = "unknown"
        return self.root_path / f"{safe}_logs.sqlite3"

    @staticmethod
    def _connect(db_path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS module_logs (
                log_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                source_module TEXT NOT NULL,
                object_id TEXT NOT NULL,
                object_label TEXT NOT NULL,
                action TEXT NOT NULL,
                action_label TEXT NOT NULL,
                status TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                operator_id TEXT NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_module_logs_module_time ON module_logs(source_module, timestamp DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_module_logs_status ON module_logs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_module_logs_object ON module_logs(object_id)")
        conn.commit()


_default_service: ModuleLogService | None = None


def get_module_log_service() -> ModuleLogService:
    global _default_service
    if _default_service is None:
        _default_service = ModuleLogService()
    return _default_service


def record_module_log(log_service: Any, **kwargs: Any) -> str | None:
    if log_service is None or not callable(getattr(log_service, "record_log", None)):
        return None
    return log_service.record_log(**kwargs)
