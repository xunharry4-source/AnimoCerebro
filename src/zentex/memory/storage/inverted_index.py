from __future__ import annotations

import sqlite3
import logging
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Dict
import enum
from threading import Lock

try:
    import jieba
except ImportError:
    jieba = None  # type: ignore

import re

logger = logging.getLogger(__name__)


def _sqlite_scalar(value: Any) -> Any:
    """Normalize values so sqlite3 parameter binding never sees arbitrary objects."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bytes)):
        return value
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _sanitize_text(value: str) -> str:
    """Remove characters that commonly break sqlite/fts bindings."""
    if not value:
        return ""
    return value.replace("\x00", "")

def is_cjk(text: str) -> bool:
    """Detect if text contains CJK (Chinese, Japanese, Korean) characters."""
    return any('\u4e00' <= char <= '\u9fff' for char in text)

class MultiModalIndex:
    """
    SQLite-backed hybrid index for Memory Engine v2.0.
    
    Provides:
    - Text Index (BM25 via FTS5) for titles, summaries, and content.
    - Metadata Index (B-tree) for trace_id, target_id, timestamps, etc.
    """

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self._lock, self._conn:
            # Enable WAL mode for concurrent performance
            self._conn.execute("PRAGMA journal_mode=WAL")
            
            # Metadata and exact match table
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_metadata (
                    memory_id TEXT PRIMARY KEY,
                    memory_layer TEXT,
                    source_kind TEXT,
                    trace_id TEXT,
                    target_id TEXT,
                    created_at TEXT,
                    tier TEXT,
                    valence TEXT,
                    tags_json TEXT,
                    schema_version INTEGER DEFAULT 2
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_trace ON memory_metadata(trace_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON memory_metadata(target_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_layer_tier ON memory_metadata(memory_layer, tier)")

            # Full-text search table (FTS5)
            # We use 'unicode61' with 'remove_diacritics 1' for broad language support.
            # Tokenization for CJK is handled via pre-processing in Python.
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    memory_id UNINDEXED,
                    title,
                    summary,
                    content,
                    tokenize='unicode61 remove_diacritics 1'
                )
            """)
            # Optimization: Set BM25 weights (Title=3.0, Summary=2.0, Content=1.0)
            # This is applied during query time, but can be hinted here if needed.

    def rebuild_storage(self) -> None:
        """Recreate the derived SQLite index from scratch.

        The FTS database is a projection of canonical memory stores, so when the
        virtual table becomes unreadable we should discard and rebuild the whole
        file instead of trying to mutate the corrupted table in place.
        """
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                logger.warning("Failed to close corrupted memory index connection", exc_info=True)

            for suffix in ("", "-wal", "-shm"):
                target = Path(f"{self.db_path}{suffix}")
                try:
                    if target.exists():
                        target.unlink()
                except Exception:
                    logger.warning("Failed to remove corrupted memory index file %s", target, exc_info=True)

            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

        self._init_db()

    def _tokenize(self, text: str) -> str:
        """Adaptive tokenizer: uses Jieba for CJK and direct pass-through for Latin."""
        if not text:
            return ""
        if jieba and is_cjk(text):
            # Jieba returns a generator, join with spaces for FTS5
            return " ".join(jieba.cut(text))
        return text

    def add_record(self, record_id: str, title: str, summary: str, content: str, metadata: Dict[str, Any]):
        """Index a memory record with multi-language tokenization.
        
        Args:
            record_id: Unique identifier for the memory record
            title: Record title (will be tokenized for search)
            summary: Record summary (will be tokenized for search)
            content: Record content (will be tokenized for search)
            metadata: Additional metadata including memory_layer, tags, etc.
            
        Raises:
            ValueError: If record_id is empty
        """
        # ✅ Validate and sanitize inputs to prevent SQLite errors
        if not record_id:
            raise ValueError("record_id cannot be empty")
        
        # Ensure text fields are strings (not None)
        title = str(title) if title is not None else ""
        summary = str(summary) if summary is not None else ""
        content = str(content) if content is not None else ""
        
        record_id = str(record_id)
        tags_json = json.dumps(metadata.get("tags", []), ensure_ascii=False, default=str)
        metadata_values = (
            record_id,
            _sqlite_scalar(metadata.get("memory_layer")),
            _sqlite_scalar(metadata.get("source_kind")),
            _sqlite_scalar(metadata.get("trace_id")),
            _sqlite_scalar(metadata.get("target_id")),
            _sqlite_scalar(metadata.get("created_at")),
            _sqlite_scalar(metadata.get("tier")),
            _sqlite_scalar(metadata.get("valence")),
            tags_json,
        )
        
        # Pre-tokenize for CJK support
        proc_title = self._tokenize(title)
        proc_summary = self._tokenize(summary)
        proc_content = self._tokenize(content)
        
        # 📝 Audit log: Index operation
        logger.debug(
            f"Indexing record: id={record_id}, layer={metadata.get('memory_layer')}, "
            f"title_len={len(proc_title)}, summary_len={len(proc_summary)}, content_len={len(proc_content)}"
        )
        
        # 🛡️ Safety: Ensure all FTS fields are valid strings (None protection)
        safe_title = _sanitize_text(proc_title if proc_title is not None else "")
        safe_summary = _sanitize_text(proc_summary if proc_summary is not None else "")
        safe_content = _sanitize_text(proc_content if proc_content is not None else "")
        
        try:
            with self._lock, self._conn:
                # Insert into metadata table
                self._conn.execute("""
                    INSERT OR REPLACE INTO memory_metadata 
                    (memory_id, memory_layer, source_kind, trace_id, target_id, created_at, tier, valence, tags_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, metadata_values)
                
                # Insert into FTS table with pre-tokenized content
                self._conn.execute("""
                    INSERT OR REPLACE INTO memory_fts (memory_id, title, summary, content)
                    VALUES (?, ?, ?, ?)
                """, (record_id, safe_title, safe_summary, safe_content))
                
            # 📝 Audit log: Success
            logger.debug(f"Successfully indexed record: {record_id}")
            
        except sqlite3.Error as e:
            # 📝 Audit log: Failure with detailed diagnostics
            logger.error(
                f"Failed to index record {record_id}: {e}. "
                f"Title: '{title[:50] if title else 'None'}...', "
                f"Summary: '{summary[:50] if summary else 'None'}...', "
                f"Content len: {len(content) if content else 0}, "
                f"Safe title type: {type(safe_title).__name__}, "
                f"Safe summary type: {type(safe_summary).__name__}, "
                f"Safe content type: {type(safe_content).__name__}"
            )
            raise

    def search(self, query: str, filters: Dict[str, Optional[Any]] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Execute hybrid search using BM25 and metadata filters.
        """
        filters = filters or {}
        where_clauses = []
        params = []

        if filters.get("memory_layer"):
            where_clauses.append("m.memory_layer = ?")
            params.append(filters["memory_layer"])
        if filters.get("trace_id"):
            where_clauses.append("m.trace_id = ?")
            params.append(filters["trace_id"])
        if filters.get("target_id"):
            where_clauses.append("m.target_id = ?")
            params.append(filters["target_id"])
        if filters.get("tier"):
            where_clauses.append("m.tier = ?")
            params.append(filters["tier"])
        if filters.get("tag"):
            where_clauses.append("EXISTS (SELECT 1 FROM json_each(m.tags_json) WHERE value = ?)")
            params.append(filters["tag"])

        where_stmt = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # If no text query, do pure metadata search
        if not query.strip():
            sql = f"""
                SELECT m.*, f.title, f.summary, f.content
                FROM memory_metadata m
                JOIN memory_fts f ON m.memory_id = f.memory_id
                WHERE {where_stmt}
                ORDER BY m.created_at DESC
                LIMIT ?
            """
            params.append(limit)
        else:
            # BM25 weighted search (Title=3, Summary=2, Content=1)
            # The weights are passed to the bm25() function.
            # We also tokenize the query to match the indexed tokens.
            proc_query = self._tokenize(query)
            sql = f"""
                SELECT m.*, f.title, f.summary, f.content, bm25(memory_fts, 3.0, 2.0, 1.0) as fts_rank
                FROM memory_fts f
                JOIN memory_metadata m ON f.memory_id = m.memory_id
                WHERE f.memory_fts MATCH ? AND {where_stmt}
                ORDER BY fts_rank
                LIMIT ?
            """
            params = [proc_query] + params + [limit]

        try:
            with self._lock:
                cursor = self._conn.execute(sql, params)
            results = []
            for row in cursor:
                item = dict(row)
                item["tags"] = json.loads(item.pop("tags_json", "[]"))
                results.append(item)
            return results
        except sqlite3.OperationalError as e:
            logger.error(f"Search failed: {e}")
            return []

    def close(self):
        with self._lock:
            self._conn.close()
