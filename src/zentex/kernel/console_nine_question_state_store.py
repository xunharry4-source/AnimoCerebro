from __future__ import annotations
"""SQLite-backed nine-question state store with per-question tables."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Optional

from zentex.nine_questions.query import COMPOSED_RECORD_SCHEMA_VERSION
from zentex.web_console.contracts.kernel_service import NineQuestionStateSnapshot

UTC = timezone.utc
logger = logging.getLogger(__name__)

QUESTION_SUMMARY_KEYS = {
    "q1": "我在那",
    "q2": "我有什么",
    "q3": "我是谁",
    "q4": "我能做什么",
    "q5": "我不能干什么",
    "q6": "如果我做了会怎样 / 代价与后果是什么",
    "q7": "我还可以做什么",
    "q8": "我现在应该做什么",
    "q9": "我应该如何行动",
}
QUESTION_IDS = tuple(QUESTION_SUMMARY_KEYS)

_STATE_SNAPSHOT_DROP_KEYS = {
    "execution_context",
    "execution_result",
    "history",
    "histories",
    "versions",
    "previous_versions",
    "historical_versions",
    "version_history",
    "snapshot_history",
    "snapshot_versions",
    "question_history",
    "question_versions",
    "question_snapshot_history",
    "question_snapshots_history",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return deepcopy(default)
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return deepcopy(default)


def _question_table(question_id: str) -> str:
    qid = str(question_id or "").strip().lower()
    if qid not in QUESTION_SUMMARY_KEYS:
        raise ValueError(f"invalid nine-question id: {question_id!r}")
    return f"nine_question_{qid}_snapshots"


def _sanitize_snapshot_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in _STATE_SNAPSHOT_DROP_KEYS:
                continue
            sanitized[key_text] = _sanitize_snapshot_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_snapshot_payload(item) for item in value]
    return value


class SQLiteStateStore:
    """Persists 9Q state metadata and each question snapshot in SQLite tables."""

    def __init__(self, db_path: str = "./data/sessions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nine_question_state_metadata (
                        session_id TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL DEFAULT 1,
                        version INTEGER NOT NULL DEFAULT 1,
                        revision INTEGER NOT NULL DEFAULT 0,
                        dirty_questions TEXT NOT NULL DEFAULT '[]',
                        last_refresh_reason TEXT,
                        snapshot_version INTEGER NOT NULL DEFAULT 9,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                for question_id in QUESTION_IDS:
                    conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {_question_table(question_id)} (
                            session_id TEXT PRIMARY KEY,
                            schema_version INTEGER NOT NULL DEFAULT {COMPOSED_RECORD_SCHEMA_VERSION},
                            record_version INTEGER NOT NULL DEFAULT 1,
                            snapshot_schema_version INTEGER NOT NULL DEFAULT {COMPOSED_RECORD_SCHEMA_VERSION},
                            snapshot_json TEXT NOT NULL,
                            llm_output_json TEXT NOT NULL DEFAULT '{{}}',
                            llm_trace_json TEXT NOT NULL DEFAULT '{{}}',
                            result_json TEXT NOT NULL DEFAULT '{{}}',
                            context_updates_json TEXT NOT NULL DEFAULT '{{}}',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                        """
                    )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nine_question_snapshot_history (
                        session_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        history_version INTEGER NOT NULL,
                        previous_record_version INTEGER NOT NULL DEFAULT 0,
                        reason TEXT NOT NULL DEFAULT '',
                        trace_id TEXT NOT NULL DEFAULT '',
                        snapshot_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (session_id, question_id, history_version)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nine_question_module_runs (
                        session_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        module_id TEXT NOT NULL,
                        schema_version INTEGER NOT NULL DEFAULT 1,
                        run_version INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT '',
                        run_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (session_id, question_id, module_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nine_question_module_outputs (
                        session_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        module_id TEXT NOT NULL,
                        schema_version INTEGER NOT NULL DEFAULT 1,
                        output_version INTEGER NOT NULL DEFAULT 1,
                        status TEXT NOT NULL DEFAULT '',
                        output_kind TEXT NOT NULL DEFAULT '',
                        output_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (session_id, question_id, module_id)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nine_question_q9_llm_tasks (
                        session_id TEXT NOT NULL,
                        task_scope TEXT NOT NULL,
                        task_index INTEGER NOT NULL,
                        task_key TEXT NOT NULL,
                        trace_id TEXT NOT NULL DEFAULT '',
                        request_id TEXT NOT NULL DEFAULT '',
                        decision_id TEXT NOT NULL DEFAULT '',
                        provider_name TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        task_name TEXT NOT NULL DEFAULT '',
                        task_description TEXT NOT NULL DEFAULT '',
                        plan_objective TEXT NOT NULL DEFAULT '',
                        q8_task_json TEXT NOT NULL DEFAULT '{}',
                        llm_input_json TEXT NOT NULL DEFAULT '{}',
                        llm_output_json TEXT NOT NULL DEFAULT '{}',
                        token_usage_json TEXT NOT NULL DEFAULT '{}',
                        elapsed_ms INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (session_id, task_scope, task_index)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_nine_question_q9_llm_tasks_session_key
                    ON nine_question_q9_llm_tasks (session_id, task_key)
                    """
                )
                conn.commit()
        except Exception:
            logger.exception("Failed to initialize SQLiteStateStore schema at %s", self.db_path)
            raise

    @staticmethod
    def _isolate_question_payload(question_id: str, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        isolated = json.loads(_json_dumps(payload))
        own_summary_key = QUESTION_SUMMARY_KEYS.get(question_id)
        if not own_summary_key:
            return isolated

        top_level = isolated.get("nine_questions")
        if isinstance(top_level, dict):
            own_value = top_level.get(own_summary_key)
            isolated["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}

        nested_context_updates = isolated.get("context_updates")
        if isinstance(nested_context_updates, dict):
            nested_summaries = nested_context_updates.get("nine_questions")
            if isinstance(nested_summaries, dict):
                own_value = nested_summaries.get(own_summary_key)
                nested_context_updates["nine_questions"] = {own_summary_key: own_value} if own_value is not None else {}

        return isolated

    @classmethod
    def _sanitize_question_snapshots(cls, snapshot_map: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(snapshot_map, dict):
            return {}

        sanitized: dict[str, dict[str, Any]] = {}
        for question_id, snapshot in snapshot_map.items():
            qid = str(question_id).strip().lower()
            if qid not in QUESTION_SUMMARY_KEYS or not isinstance(snapshot, dict):
                continue
            normalized = _sanitize_snapshot_payload(json.loads(_json_dumps(snapshot)))

            result_payload = normalized.get("result")
            if isinstance(result_payload, dict):
                normalized["result"] = cls._isolate_question_payload(qid, result_payload)

            context_updates = normalized.get("context_updates")
            if isinstance(context_updates, dict):
                normalized["context_updates"] = cls._isolate_question_payload(qid, context_updates)

            sanitized[qid] = normalized
        return sanitized

    @staticmethod
    def _extract_llm_output(question_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        try:
            from zentex.common.nine_questions_shared import project_authoritative_question_llm_output

            projected = project_authoritative_question_llm_output(question_id, snapshot)
            return projected if isinstance(projected, dict) else {}
        except Exception:
            logger.exception("Failed to project LLM output for %s", question_id)
            return {}

    @staticmethod
    def _extract_module_runs(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        direct = snapshot.get("module_runs")
        if isinstance(direct, list):
            return [deepcopy(item) for item in direct if isinstance(item, dict)]
        context_updates = snapshot.get("context_updates")
        if isinstance(context_updates, dict):
            for key, value in context_updates.items():
                if str(key).endswith("_execution_diagnosis") and isinstance(value, dict):
                    runs = value.get("module_runs")
                    if isinstance(runs, list):
                        return [deepcopy(item) for item in runs if isinstance(item, dict)]
        return []

    @staticmethod
    def _extract_module_outputs(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        outputs = snapshot.get("module_outputs")
        return deepcopy(outputs) if isinstance(outputs, dict) else {}

    @staticmethod
    def _normalize_llm_trace_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        normalized = deepcopy(payload)

        def _has_material_trace(item: Any) -> bool:
            if not isinstance(item, dict):
                return False
            return any(
                item.get(key) not in (None, "", [], {})
                for key in ("provider_name", "model", "prompt", "context_data", "raw_response", "error_type", "error_message")
            )

        def _normalize_invocation(item: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
            invocation = deepcopy(item)
            for key in (
                "request_id",
                "decision_id",
                "provider_name",
                "model",
                "system_prompt",
                "prompt",
                "source_module",
                "invocation_phase",
                "question_driver_refs",
                "context_data",
                "raw_response",
                "elapsed_ms",
                "error_type",
                "error_message",
            ):
                if key not in invocation and key in root:
                    invocation[key] = deepcopy(root.get(key))

            token_usage = invocation.get("token_usage")
            token_usage = token_usage if isinstance(token_usage, dict) else {}
            invocation["token_usage"] = {
                "input_tokens": int(token_usage.get("input_tokens") or 0),
                "output_tokens": int(token_usage.get("output_tokens") or 0),
                "total_tokens": int(token_usage.get("total_tokens") or 0),
            }
            invocation.setdefault("error_type", None)
            invocation.setdefault("error_message", None)
            invocation.setdefault("elapsed_ms", 0)
            return invocation

        invocations = normalized.get("invocations")
        if isinstance(invocations, list):
            material_invocations = [
                _normalize_invocation(item, normalized)
                for item in invocations
                if isinstance(item, dict) and _has_material_trace(item)
            ]
        elif _has_material_trace(normalized):
            material_invocations = [_normalize_invocation(normalized, normalized)]
        else:
            return {}

        if not material_invocations:
            return {}

        primary = dict(material_invocations[-1])
        if isinstance(normalized.get("asset_scopes"), list) and normalized.get("asset_scopes"):
            for key in (
                "request_id",
                "decision_id",
                "provider_name",
                "model",
                "system_prompt",
                "prompt",
                "source_module",
                "invocation_phase",
                "question_driver_refs",
                "context_data",
                "raw_response",
                "asset_scopes",
                "internal_tool_llm_trace_payload",
                "external_tool_llm_trace_payload",
            ):
                if normalized.get(key) not in (None, "", [], {}):
                    primary[key] = deepcopy(normalized.get(key))
        primary["invocations"] = material_invocations
        primary["token_usage"] = {
            "input_tokens": sum(int((item.get("token_usage") or {}).get("input_tokens") or 0) for item in material_invocations),
            "output_tokens": sum(int((item.get("token_usage") or {}).get("output_tokens") or 0) for item in material_invocations),
            "total_tokens": sum(int((item.get("token_usage") or {}).get("total_tokens") or 0) for item in material_invocations),
        }
        primary["elapsed_ms"] = sum(int(item.get("elapsed_ms") or 0) for item in material_invocations)
        primary.setdefault("error_type", None)
        primary.setdefault("error_message", None)
        return primary

    async def get(self, session_id: str) -> Optional[NineQuestionStateSnapshot]:
        return await asyncio.to_thread(self._get_sync, session_id)

    async def get_metadata(self, session_id: str) -> Optional[dict[str, Any]]:
        return await asyncio.to_thread(self._get_metadata_sync, session_id)

    async def get_question_snapshot(self, session_id: str, question_id: str) -> Optional[dict[str, Any]]:
        snapshots = await self.get_question_snapshots(session_id, [question_id])
        return snapshots.get(str(question_id).strip().lower())

    async def get_question_snapshots(self, session_id: str, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._get_question_snapshots_sync, session_id, question_ids)

    async def get_question_summary_rows(self, session_id: str, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._get_question_summary_rows_sync, session_id, question_ids)

    async def append_question_snapshot_history(
        self,
        session_id: str,
        question_id: str,
        snapshot: dict[str, Any],
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._append_question_snapshot_history_sync,
            session_id,
            question_id,
            snapshot,
            reason,
        )

    async def get_question_snapshot_history(
        self,
        session_id: str,
        question_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get_question_snapshot_history_sync,
            session_id,
            question_id,
            limit,
        )

    async def get_question_module_runs(
        self,
        session_id: str,
        question_id: str,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get_question_module_runs_sync,
            session_id,
            question_id,
        )

    async def get_question_module_outputs(
        self,
        session_id: str,
        question_id: str,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._get_question_module_outputs_sync,
            session_id,
            question_id,
        )

    async def save(self, session_id: str, state: NineQuestionStateSnapshot) -> None:
        await asyncio.to_thread(self._save_sync, session_id, state)

    def _get_sync(self, session_id: str) -> Optional[NineQuestionStateSnapshot]:
        started = time.monotonic()
        metadata = self._get_metadata_sync(session_id)
        if metadata is None:
            return None
        snapshots = self._get_question_snapshots_sync(session_id, list(QUESTION_IDS))
        snapshot_history = {
            question_id: history
            for question_id in QUESTION_IDS
            if (history := self._get_question_snapshot_history_sync(session_id, question_id, 20))
        }
        elapsed = time.monotonic() - started
        if elapsed >= 1.0:
            logger.warning("SQLiteStateStore.get slow session_id=%s elapsed=%.3fs", session_id, elapsed)
        return NineQuestionStateSnapshot(
            version=int(metadata["version"]),
            revision=int(metadata["revision"]),
            dirty_questions=list(metadata["dirty_questions"]),
            question_snapshots=snapshots,
            question_snapshots_history=snapshot_history,
            last_refresh_reason=metadata.get("last_refresh_reason"),
            snapshot_version=int(metadata["snapshot_version"]),
            updated_at=metadata["updated_at"],
        )

    def _get_metadata_sync(self, session_id: str) -> Optional[dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT version, revision, dirty_questions, last_refresh_reason, snapshot_version, updated_at
                FROM nine_question_state_metadata
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "version": row["version"],
            "revision": row["revision"],
            "dirty_questions": _json_loads(row["dirty_questions"], []),
            "last_refresh_reason": row["last_refresh_reason"],
            "snapshot_version": row["snapshot_version"],
            "updated_at": datetime.fromisoformat(str(row["updated_at"])),
        }

    def _read_module_runs_sync(self, conn: sqlite3.Connection, session_id: str, question_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT run_json
            FROM nine_question_module_runs
            WHERE session_id = ? AND question_id = ?
            ORDER BY updated_at ASC, module_id ASC
            """,
            (session_id, question_id),
        ).fetchall()
        return [payload for row in rows if isinstance((payload := _json_loads(row["run_json"], {})), dict)]

    def _read_module_outputs_sync(self, conn: sqlite3.Connection, session_id: str, question_id: str) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT module_id, output_json
            FROM nine_question_module_outputs
            WHERE session_id = ? AND question_id = ?
            ORDER BY updated_at ASC, module_id ASC
            """,
            (session_id, question_id),
        ).fetchall()
        outputs: dict[str, Any] = {}
        for row in rows:
            payload = _json_loads(row["output_json"], {})
            if isinstance(payload, dict):
                outputs[str(row["module_id"])] = payload
        return outputs

    def _get_question_module_runs_sync(self, session_id: str, question_id: str) -> list[dict[str, Any]]:
        normalized_question_id = str(question_id or "").strip().lower()
        if normalized_question_id not in QUESTION_IDS:
            return []
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            return self._read_module_runs_sync(conn, session_id, normalized_question_id)

    def _get_question_module_outputs_sync(self, session_id: str, question_id: str) -> dict[str, Any]:
        normalized_question_id = str(question_id or "").strip().lower()
        if normalized_question_id not in QUESTION_IDS:
            return {}
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            return self._read_module_outputs_sync(conn, session_id, normalized_question_id)

    def _get_question_snapshots_sync(self, session_id: str, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = [
            str(question_id).strip().lower()
            for question_id in question_ids
            if str(question_id).strip().lower() in QUESTION_SUMMARY_KEYS
        ]
        if not normalized_ids:
            return {}

        snapshots: dict[str, dict[str, Any]] = {}
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            for question_id in normalized_ids:
                row = conn.execute(
                    f"""
                    SELECT snapshot_json, llm_output_json, llm_trace_json
                    FROM {_question_table(question_id)}
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    continue
                snapshot = _json_loads(row["snapshot_json"], {})
                if not isinstance(snapshot, dict):
                    continue
                llm_output = _json_loads(row["llm_output_json"], {})
                llm_business_keys = (
                    set(llm_output)
                    - {"summary", "trace_id", "tool_id", "timestamp", "generated_at", "updated_at", "confidence"}
                    if isinstance(llm_output, dict)
                    else set()
                )
                if isinstance(llm_output, dict) and llm_business_keys:
                    snapshot["llm_output"] = llm_output
                llm_trace = _json_loads(row["llm_trace_json"], {})
                if isinstance(llm_trace, dict) and llm_trace:
                    snapshot["llm_trace_payload"] = llm_trace
                module_outputs = self._read_module_outputs_sync(conn, session_id, question_id)
                if module_outputs:
                    snapshot["module_outputs"] = module_outputs
                module_runs = self._read_module_runs_sync(conn, session_id, question_id)
                if module_runs:
                    snapshot["module_runs"] = module_runs
                sanitized = self._sanitize_question_snapshots({question_id: snapshot}).get(question_id)
                if isinstance(sanitized, dict):
                    snapshots[question_id] = sanitized
        return snapshots

    def _get_question_summary_rows_sync(self, session_id: str, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = [
            str(question_id).strip().lower()
            for question_id in question_ids
            if str(question_id).strip().lower() in QUESTION_SUMMARY_KEYS
        ]
        if not normalized_ids:
            return {}

        rows_by_question: dict[str, dict[str, Any]] = {}
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            for question_id in normalized_ids:
                row = conn.execute(
                    f"""
                    SELECT snapshot_json, llm_trace_json, updated_at
                    FROM {_question_table(question_id)}
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    continue
                snapshot = _json_loads(row["snapshot_json"], {})
                if not isinstance(snapshot, dict):
                    continue
                llm_trace = _json_loads(row["llm_trace_json"], {})
                llm_trace = llm_trace if isinstance(llm_trace, dict) else {}
                provider_name = str(snapshot.get("provider_name") or llm_trace.get("provider_name") or "").strip()
                if not provider_name:
                    invocations = llm_trace.get("invocations")
                    if isinstance(invocations, list):
                        for invocation in invocations:
                            if not isinstance(invocation, dict):
                                continue
                            provider_name = str(invocation.get("provider_name") or "").strip()
                            if provider_name:
                                break
                rows_by_question[question_id] = {
                    "question_id": question_id,
                    "tool_id": snapshot.get("tool_id"),
                    "summary": snapshot.get("summary"),
                    "confidence": snapshot.get("confidence"),
                    "trace_id": snapshot.get("trace_id"),
                    "timestamp": snapshot.get("timestamp") or row["updated_at"],
                    "cache_status": snapshot.get("cache_status"),
                    "provider_name": provider_name or None,
                    "mounted_plugins": deepcopy(snapshot.get("mounted_plugins")) if isinstance(snapshot.get("mounted_plugins"), list) else [],
                }
        return rows_by_question

    def _append_question_snapshot_history_sync(
        self,
        session_id: str,
        question_id: str,
        snapshot: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        qid = str(question_id).strip().lower()
        if qid not in QUESTION_SUMMARY_KEYS:
            raise ValueError(f"invalid nine-question id: {question_id!r}")
        if not isinstance(snapshot, dict) or not snapshot:
            raise ValueError("history snapshot must be a non-empty dictionary")

        now = _utc_now_iso()
        sanitized = self._sanitize_question_snapshots({qid: snapshot}).get(qid) or {}
        if not sanitized:
            raise ValueError("history snapshot has no persistable payload")

        trace_id = str(sanitized.get("trace_id") or "").strip()
        table = _question_table(qid)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                f"SELECT record_version FROM {table} WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            previous_record_version = int(existing["record_version"]) if existing else 0
            latest_history = conn.execute(
                """
                SELECT COALESCE(MAX(history_version), 0) AS latest_version
                FROM nine_question_snapshot_history
                WHERE session_id = ? AND question_id = ?
                """,
                (session_id, qid),
            ).fetchone()
            history_version = int(latest_history["latest_version"] or 0) + 1
            conn.execute(
                """
                INSERT INTO nine_question_snapshot_history
                (session_id, question_id, history_version, previous_record_version,
                 reason, trace_id, snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    qid,
                    history_version,
                    previous_record_version,
                    str(reason or ""),
                    trace_id,
                    _json_dumps(sanitized),
                    now,
                ),
            )
            conn.commit()

        return {
            "session_id": session_id,
            "question_id": qid,
            "history_version": history_version,
            "previous_record_version": previous_record_version,
            "reason": str(reason or ""),
            "trace_id": trace_id,
            "snapshot": sanitized,
            "created_at": now,
        }

    def _get_question_snapshot_history_sync(
        self,
        session_id: str,
        question_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        qid = str(question_id).strip().lower()
        if qid not in QUESTION_SUMMARY_KEYS:
            raise ValueError(f"invalid nine-question id: {question_id!r}")
        try:
            row_limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            row_limit = 20

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, question_id, history_version, previous_record_version,
                       reason, trace_id, snapshot_json, created_at
                FROM nine_question_snapshot_history
                WHERE session_id = ? AND question_id = ?
                ORDER BY history_version DESC
                LIMIT ?
                """,
                (session_id, qid, row_limit),
            ).fetchall()

        history: list[dict[str, Any]] = []
        for row in rows:
            snapshot = _json_loads(row["snapshot_json"], {})
            if not isinstance(snapshot, dict):
                snapshot = {}
            history.append(
                {
                    "session_id": row["session_id"],
                    "question_id": row["question_id"],
                    "history_version": int(row["history_version"]),
                    "previous_record_version": int(row["previous_record_version"]),
                    "reason": row["reason"],
                    "trace_id": row["trace_id"],
                    "snapshot": snapshot,
                    "created_at": row["created_at"],
                }
            )
        return history

    def _save_sync(self, session_id: str, state: NineQuestionStateSnapshot) -> None:
        started = time.monotonic()
        now = _utc_now_iso()
        sanitized_question_snapshots = self._sanitize_question_snapshots(state.question_snapshots)
        state.question_snapshots = sanitized_question_snapshots
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN")
                existing = conn.execute(
                    "SELECT created_at FROM nine_question_state_metadata WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                created_at = str(existing["created_at"]) if existing else now
                conn.execute(
                    """
                    INSERT INTO nine_question_state_metadata
                    (session_id, schema_version, version, revision, dirty_questions, last_refresh_reason,
                     snapshot_version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        version = excluded.version,
                        revision = excluded.revision,
                        dirty_questions = excluded.dirty_questions,
                        last_refresh_reason = excluded.last_refresh_reason,
                        snapshot_version = excluded.snapshot_version,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        1,
                        state.version,
                        state.revision,
                        _json_dumps(state.dirty_questions),
                        state.last_refresh_reason,
                        state.snapshot_version,
                        created_at,
                        now,
                    ),
                )

                for question_id, snapshot in sanitized_question_snapshots.items():
                    self._save_question_snapshot_sync(conn, session_id, question_id, snapshot, now)
                conn.commit()
            elapsed = time.monotonic() - started
            if elapsed >= 1.0:
                logger.warning("SQLiteStateStore.save slow session_id=%s elapsed=%.3fs", session_id, elapsed)
        except Exception:
            logger.exception("Failed to persist nine-question state for session_id=%s", session_id)
            raise

    def _save_question_snapshot_sync(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        question_id: str,
        snapshot: dict[str, Any],
        now: str,
    ) -> None:
        table = _question_table(question_id)
        existing = conn.execute(
            f"SELECT record_version, created_at FROM {table} WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        record_version = int(existing["record_version"]) + 1 if existing else 1
        created_at = str(existing["created_at"]) if existing else now
        result_payload = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
        context_updates = snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {}
        snapshot_trace = snapshot.get("llm_trace_payload")
        context_trace = context_updates.get("llm_trace_payload")
        result_trace = result_payload.get("llm_trace_payload")
        llm_trace_source = snapshot_trace or context_trace or result_trace
        for candidate in (context_trace, result_trace, snapshot_trace):
            if isinstance(candidate, dict) and isinstance(candidate.get("asset_scopes"), list) and candidate.get("asset_scopes"):
                llm_trace_source = candidate
                break
        llm_trace = self._normalize_llm_trace_payload(llm_trace_source)
        if llm_trace:
            snapshot = dict(snapshot)
            snapshot["llm_trace_payload"] = llm_trace
        llm_output = self._extract_llm_output(question_id, snapshot)

        conn.execute(
            f"""
            INSERT INTO {table}
            (session_id, schema_version, record_version, snapshot_schema_version, snapshot_json,
             llm_output_json, llm_trace_json, result_json, context_updates_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                schema_version = excluded.schema_version,
                record_version = excluded.record_version,
                snapshot_schema_version = excluded.snapshot_schema_version,
                snapshot_json = excluded.snapshot_json,
                llm_output_json = excluded.llm_output_json,
                llm_trace_json = excluded.llm_trace_json,
                result_json = excluded.result_json,
                context_updates_json = excluded.context_updates_json,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                COMPOSED_RECORD_SCHEMA_VERSION,
                record_version,
                int(snapshot.get("snapshot_schema_version") or COMPOSED_RECORD_SCHEMA_VERSION),
                _json_dumps(snapshot),
                _json_dumps(llm_output),
                _json_dumps(llm_trace),
                _json_dumps(result_payload),
                _json_dumps(context_updates),
                created_at,
                now,
            ),
        )

        if question_id not in {"q1", "q2", "q3"}:
            for run in self._extract_module_runs(snapshot):
                module_id = str(run.get("module_id") or "").strip()
                if not module_id:
                    continue
                existing_run = conn.execute(
                    """
                    SELECT run_version, created_at
                    FROM nine_question_module_runs
                    WHERE session_id = ? AND question_id = ? AND module_id = ?
                    """,
                    (session_id, question_id, module_id),
                ).fetchone()
                run_version = int(existing_run["run_version"]) + 1 if existing_run else 1
                run_created_at = str(existing_run["created_at"]) if existing_run else now
                conn.execute(
                    """
                    INSERT INTO nine_question_module_runs
                    (session_id, question_id, module_id, schema_version, run_version, status, run_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, question_id, module_id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        run_version = excluded.run_version,
                        status = excluded.status,
                        run_json = excluded.run_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        question_id,
                        module_id,
                        1,
                        run_version,
                        str(run.get("status") or ""),
                        _json_dumps(run),
                        run_created_at,
                        now,
                    ),
                )

            for module_id, output in self._extract_module_outputs(snapshot).items():
                if not isinstance(output, dict):
                    continue
                module_text = str(module_id or output.get("module_id") or "").strip()
                if not module_text:
                    continue
                existing_output = conn.execute(
                    """
                    SELECT output_version, created_at
                    FROM nine_question_module_outputs
                    WHERE session_id = ? AND question_id = ? AND module_id = ?
                    """,
                    (session_id, question_id, module_text),
                ).fetchone()
                output_version = int(existing_output["output_version"]) + 1 if existing_output else 1
                output_created_at = str(existing_output["created_at"]) if existing_output else now
                conn.execute(
                    """
                    INSERT INTO nine_question_module_outputs
                    (session_id, question_id, module_id, schema_version, output_version, status,
                     output_kind, output_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, question_id, module_id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        output_version = excluded.output_version,
                        status = excluded.status,
                        output_kind = excluded.output_kind,
                        output_json = excluded.output_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        question_id,
                        module_text,
                        1,
                        output_version,
                        str(output.get("status") or ""),
                        str(output.get("output_kind") or ""),
                        _json_dumps(output),
                        output_created_at,
                        now,
                    ),
                )
