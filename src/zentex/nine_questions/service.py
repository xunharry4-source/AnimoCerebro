from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

from .query import (
    COMPOSED_RECORD_SCHEMA_VERSION,
    _build_flat_upstream_context as _query_build_flat_upstream_context,
    build_question_record,
)
from zentex.nine_questions.config import load_nine_questions_execute_all_config
from zentex.common.flow_audit import FlowAudit
from zentex.kernel.cognition_flow.models import BootstrapStatus, NineQuestionState

# Internal SQLite state manager key — nine-questions are global, not per-session.
_NQ_STATE_KEY = "nq-baseline"
_Q2_SNAPSHOT_TABLE = "nine_question_q2_snapshots"

EXPECTED_QUESTION_IDS = tuple(f"q{i}" for i in range(1, 10))
_QUALIFIED_SNAPSHOT_STATUSES = {"completed", "ready"}
_UNQUALIFIED_MODULE_STATUSES = {"failed", "missing", "degraded", "partial", "partial_failed", "abnormal", "stopped"}


class NineQuestionService:
    """Single query/execute entry for nine-question state.

    Nine-questions represent the agent's global cognitive baseline and are NOT
    scoped to HTTP sessions or user sessions.  All methods operate on the single
    shared baseline; no session_id parameter is exposed in the public API.
    """

    def __init__(
        self,
        *,
        facade: Any,
        state_manager: Any,
        storage_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self._facade = facade
        self._state_manager = state_manager
        if storage_root is None:
            from zentex.common.storage_paths import get_storage_paths

            storage_root = get_storage_paths().nine_questions_dir
        self._storage_root = Path(storage_root)

    @staticmethod
    def _normalize_dirty_questions(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return sorted(dict.fromkeys(normalized))

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _bootstrap_status_value(status: Any) -> str:
        return str(getattr(status, "value", status) or "").strip().lower()

    @classmethod
    def _question_run_error_summary(cls, state: Any, question_id: str) -> str:
        if isinstance(state, dict):
            responses = state.get("responses")
            response = responses.get(question_id) if isinstance(responses, dict) else None
            if isinstance(response, dict):
                error = str(response.get("error") or "").strip()
                if error:
                    return error
            snapshot = cls.get_question_snapshot_map(state).get(question_id)
            diagnosis = cls._extract_snapshot_diagnosis(snapshot)
            for module in diagnosis.get("module_runs") or []:
                if not isinstance(module, dict):
                    continue
                error_message = str(module.get("error_message") or "").strip()
                error_code = str(module.get("error_code") or "").strip()
                if error_message or error_code:
                    return ": ".join(item for item in (error_code, error_message) if item)
            return ""

        responses = getattr(state, "responses", None)
        response = responses.get(question_id) if isinstance(responses, dict) else None
        return str(getattr(response, "error", "") or "").strip()

    @staticmethod
    def _normalize_schema_version(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 0
        return max(parsed, COMPOSED_RECORD_SCHEMA_VERSION)

    @classmethod
    def _normalize_snapshot_metadata(
        cls,
        snapshot: dict[str, Any],
        *,
        now_iso: str,
        touch_updated_at: bool,
    ) -> dict[str, Any]:
        normalized = deepcopy(snapshot)
        timestamp = str(normalized.get("timestamp") or "").strip()
        generated_at = str(normalized.get("generated_at") or "").strip()

        if not timestamp:
            timestamp = generated_at or now_iso
        if not generated_at:
            generated_at = timestamp

        normalized["timestamp"] = timestamp
        normalized["generated_at"] = generated_at
        if touch_updated_at or not str(normalized.get("updated_at") or "").strip():
            normalized["updated_at"] = now_iso
        normalized["snapshot_schema_version"] = cls._normalize_schema_version(
            normalized.get("snapshot_schema_version")
        )
        normalized["composed_schema_version"] = cls._normalize_schema_version(
            normalized.get("composed_schema_version")
        )
        return normalized

    @classmethod
    def _normalize_snapshot_map_metadata(
        cls,
        snapshot_map: dict[str, Any],
        *,
        touch_updated_at: bool,
    ) -> dict[str, dict[str, Any]]:
        now_iso = cls._now_iso()
        normalized: dict[str, dict[str, Any]] = {}
        for question_id, snapshot in snapshot_map.items():
            if not isinstance(snapshot, dict):
                continue
            normalized[str(question_id)] = cls._normalize_snapshot_metadata(
                snapshot,
                now_iso=now_iso,
                touch_updated_at=touch_updated_at,
            )
        return normalized

    @staticmethod
    def _merge_snapshot_patch(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(current)
        for key, value in patch.items():
            if key in {"context_updates", "result"} and isinstance(value, dict):
                existing = merged.get(key)
                if not isinstance(existing, dict):
                    existing = {}
                combined = deepcopy(existing)
                combined.update(deepcopy(value))
                merged[key] = combined
            else:
                merged[key] = deepcopy(value)
        return merged

    @staticmethod
    def _prune_q3_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        pruned = deepcopy(snapshot)
        pruned.pop("module_runs", None)
        pruned.pop("module_outputs", None)
        pruned.pop("llm_trace_payload", None)

        context_updates = pruned.get("context_updates")
        if isinstance(context_updates, dict):
            context_updates = deepcopy(context_updates)
            context_updates.pop("q3_execution_diagnosis", None)
            context_updates.pop("llm_trace_payload", None)
            pruned["context_updates"] = context_updates

        result = pruned.get("result")
        if isinstance(result, dict):
            result = deepcopy(result)
            result.pop("context_updates", None)
            result.pop("llm_trace_payload", None)
            result.pop("evidence", None)
            pruned["result"] = result

        llm_output = pruned.get("llm_output")
        if isinstance(llm_output, dict):
            llm_output = deepcopy(llm_output)
            llm_output.pop("q3_execution_diagnosis", None)
            pruned["llm_output"] = llm_output

        return pruned

    @classmethod
    def _append_question_history_version(
        cls,
        *,
        question_id: str,
        current_snapshot: dict[str, Any],
        new_snapshot: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Return only the latest canonical snapshot.

        Historical versions are stored in the independent snapshot history
        table, never embedded in the latest snapshot payload.
        """
        merged = deepcopy(new_snapshot)
        for key in (
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
        ):
            merged.pop(key, None)
        return merged

    async def _persist_question_history_version(
        self,
        *,
        question_id: str,
        current_snapshot: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        if not self.snapshot_has_usable_data(current_snapshot):
            return {}
        append_history = getattr(self._state_manager, "append_question_snapshot_history", None)
        if not callable(append_history):
            fallback_store = getattr(self._state_manager, "_store", None)
            append_history = getattr(fallback_store, "append_question_snapshot_history", None)
        if not callable(append_history):
            raise RuntimeError("Nine-question snapshot history store is unavailable")
        entry = await append_history(
            _NQ_STATE_KEY,
            question_id,
            deepcopy(current_snapshot),
            reason=reason,
        )
        return deepcopy(entry) if isinstance(entry, dict) else {}

    @staticmethod
    def _history_update_payload(question_id: str, history_entry: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(history_entry, dict) or not history_entry:
            return {}
        return {"question_snapshots_history": {str(question_id).strip().lower(): [deepcopy(history_entry)]}}

    @staticmethod
    def _serialize_state_payload(state: Any) -> dict[str, Any]:
        if isinstance(state, dict):
            return deepcopy(state)
        if hasattr(state, "to_dict") and callable(getattr(state, "to_dict", None)):
            payload = state.to_dict()
            return deepcopy(payload) if isinstance(payload, dict) else {}
        if hasattr(state, "model_dump") and callable(getattr(state, "model_dump", None)):
            payload = state.model_dump(mode="json")
            return deepcopy(payload) if isinstance(payload, dict) else {}
        return {}

    @staticmethod
    def _extract_snapshot_diagnosis(snapshot: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            return {}
        for payload in (
            snapshot.get("context_updates"),
            ((snapshot.get("result") or {}).get("context_updates") if isinstance(snapshot.get("result"), dict) else None),
            ((snapshot.get("execution_result") or {}).get("context_updates") if isinstance(snapshot.get("execution_result"), dict) else None),
        ):
            if not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if str(key).endswith("_execution_diagnosis") and isinstance(value, dict):
                    return deepcopy(value)
        return {}

    @staticmethod
    def _meaningful_payload_size(value: Any) -> int:
        if isinstance(value, dict):
            return sum(NineQuestionService._meaningful_payload_size(item) for item in value.values() if item not in (None, "", [], {}))
        if isinstance(value, list):
            return sum(NineQuestionService._meaningful_payload_size(item) for item in value if item not in (None, "", [], {}))
        return 1 if value not in (None, "", [], {}) else 0

    @classmethod
    def _snapshot_health_metrics(cls, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            return {
                "authenticity_rank": 0,
                "completed_modules": 0,
                "nonempty_payload_size": 0,
                "failed_modules": 0,
                "has_real_trace": False,
                "has_summary": False,
            }

        diagnosis = cls._extract_snapshot_diagnosis(snapshot)
        authenticity = str(diagnosis.get("authenticity_status") or "").strip().lower()
        authenticity_rank = {
            "completed": 5,
            "ready": 5,
            "partial": 4,
            "partial_failed": 3,
            "degraded": 2,
            "failed": 1,
            "missing": 0,
        }.get(authenticity, 0)
        module_runs = diagnosis.get("module_runs") if isinstance(diagnosis.get("module_runs"), list) else []
        completed_modules = sum(
            1
            for item in module_runs
            if isinstance(item, dict) and str(item.get("status") or "") in {"completed", "ready"}
        )
        failed_modules = sum(
            1
            for item in module_runs
            if isinstance(item, dict)
            and str(item.get("status") or "").strip().lower() in _UNQUALIFIED_MODULE_STATUSES
        )
        trace_id = str(snapshot.get("trace_id") or "").strip()
        summary = str(snapshot.get("summary") or "").strip()
        payload_size = cls._meaningful_payload_size(snapshot.get("result")) + cls._meaningful_payload_size(snapshot.get("context_updates"))

        return {
            "authenticity_rank": authenticity_rank,
            "completed_modules": completed_modules,
            "nonempty_payload_size": payload_size,
            "failed_modules": failed_modules,
            "has_real_trace": bool(trace_id and not trace_id.endswith(":no-trace")),
            "has_summary": bool(summary),
        }

    @staticmethod
    def _rejected_diagnosis_key(canonical_key: str) -> str:
        key = str(canonical_key or "").strip()
        if key.endswith("_execution_diagnosis"):
            return f"{key.removesuffix('_execution_diagnosis')}_rejected_execution_diagnosis"
        return f"rejected_{key}" if key else "rejected_execution_diagnosis"

    @classmethod
    def _snapshot_is_intrinsically_qualified(cls, snapshot: Any) -> bool:
        if not isinstance(snapshot, dict) or not cls.snapshot_has_usable_data(snapshot):
            return False

        diagnosis = cls._extract_snapshot_diagnosis(snapshot)
        authenticity = str(diagnosis.get("authenticity_status") or "").strip().lower()
        if authenticity not in _QUALIFIED_SNAPSHOT_STATUSES:
            return False
        if diagnosis.get("snapshot_fallback_used") is True or diagnosis.get("used_fallback") is True:
            return False

        module_runs = diagnosis.get("module_runs")
        if not isinstance(module_runs, list) or not module_runs:
            return False
        for module in module_runs:
            if not isinstance(module, dict):
                return False
            status = str(module.get("status") or "").strip().lower()
            if status in _UNQUALIFIED_MODULE_STATUSES:
                return False
            if status not in _QUALIFIED_SNAPSHOT_STATUSES:
                return False
        return True

    @staticmethod
    def _question_order(question_id: str) -> int:
        qid = str(question_id or "").strip().lower()
        if len(qid) >= 2 and qid[0] == "q" and qid[1:].isdigit():
            return int(qid[1:])
        return 0

    @classmethod
    def _required_upstream_questions(cls, question_id: str) -> list[str]:
        current_order = cls._question_order(question_id)
        if current_order <= 1:
            return []
        return [f"q{i}" for i in range(1, current_order)]

    @staticmethod
    def _snapshot_generated_at_epoch(snapshot: dict[str, Any]) -> float:
        for key in ("updated_at", "generated_at", "timestamp"):
            raw = str(snapshot.get(key) or "").strip()
            if not raw:
                continue
            try:
                normalized = raw.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized).timestamp()
            except Exception:
                continue
        return 0.0

    @classmethod
    def _evaluate_snapshot_qualification(
        cls,
        *,
        question_id: str,
        snapshot: Any,
        state: Any,
    ) -> tuple[bool, str]:
        if not isinstance(snapshot, dict) or not snapshot:
            return False, f"{question_id}:missing_snapshot"
        if not cls.snapshot_has_usable_data(snapshot):
            return False, f"{question_id}:snapshot_not_usable"

        diagnosis = cls._extract_snapshot_diagnosis(snapshot)
        authenticity = str(diagnosis.get("authenticity_status") or "").strip().lower()
        if authenticity not in _QUALIFIED_SNAPSHOT_STATUSES:
            return False, f"{question_id}:authenticity_not_qualified:{authenticity or 'missing'}"

        if diagnosis.get("snapshot_fallback_used") is True or diagnosis.get("used_fallback") is True:
            return False, f"{question_id}:fallback_used"

        module_runs = diagnosis.get("module_runs")
        if not isinstance(module_runs, list) or not module_runs:
            return False, f"{question_id}:module_runs_missing"

        for module in module_runs:
            if not isinstance(module, dict):
                return False, f"{question_id}:module_run_invalid"
            status = str(module.get("status") or "").strip().lower()
            if status in _UNQUALIFIED_MODULE_STATUSES:
                module_id = str(module.get("module_id") or "unknown")
                return False, f"{question_id}:module_unqualified:{module_id}:{status}"
            if status not in _QUALIFIED_SNAPSHOT_STATUSES:
                module_id = str(module.get("module_id") or "unknown")
                return False, f"{question_id}:module_status_unknown:{module_id}:{status or 'missing'}"

        dirty_questions = (
            cls._normalize_dirty_questions(state.get("dirty_questions", []))
            if isinstance(state, dict)
            else cls._normalize_dirty_questions(getattr(state, "dirty_questions", []))
        )
        if question_id in dirty_questions:
            return False, f"{question_id}:marked_dirty"

        snapshot_epoch = cls._snapshot_generated_at_epoch(snapshot)
        if snapshot_epoch <= 0:
            return False, f"{question_id}:missing_snapshot_timestamp"

        return True, "qualified"

    async def assert_latest_qualified_upstreams(self, question_id: str) -> dict[str, Any]:
        """Validate that QN can only read upstream latest qualified snapshots.

        Raises RuntimeError when any required upstream snapshot is missing,
        dirty, fallback-based, or non-completed.
        """
        qid = str(question_id or "").strip().lower()
        required = self._required_upstream_questions(qid)
        if not required:
            state = await self.get_state()
            return self._build_scoped_upstream_state_payload(
                state,
                question_id=qid,
                upstream_question_ids=[],
            )

        state = await self.get_state()
        snapshot_map = self.get_question_snapshot_map(state)
        failures: list[str] = []
        for upstream_q in required:
            snapshot = snapshot_map.get(upstream_q)
            qualified, reason = self._evaluate_snapshot_qualification(
                question_id=upstream_q,
                snapshot=snapshot,
                state=state,
            )
            if not qualified:
                failures.append(reason)

        if failures:
            raise RuntimeError(
                "Upstream latest qualified snapshot gate failed for "
                f"{qid}: {', '.join(failures)}"
            )

        return self._build_scoped_upstream_state_payload(
            state,
            question_id=qid,
            upstream_question_ids=required,
        )

    def _build_scoped_upstream_state_payload(
        self,
        state: Any,
        *,
        question_id: str,
        upstream_question_ids: list[str],
    ) -> dict[str, Any]:
        from zentex.common.nine_questions_shared import build_authoritative_question_llm_snapshot

        source = self._serialize_state_payload(state)
        snapshot_map = self.get_question_snapshot_map(source)
        scoped_snapshots = {
            upstream_q: build_authoritative_question_llm_snapshot(upstream_q, snapshot_map[upstream_q])
            for upstream_q in upstream_question_ids
            if isinstance(snapshot_map.get(upstream_q), dict)
        }
        return {
            "session_id": source.get("session_id") or _NQ_STATE_KEY,
            "bootstrap_status": source.get("bootstrap_status"),
            "last_updated_at": source.get("last_updated_at") or source.get("updated_at"),
            "revision": source.get("revision"),
            "snapshot_version": source.get("snapshot_version"),
            "dirty_questions": [
                item
                for item in self._normalize_dirty_questions(source.get("dirty_questions", []))
                if item in upstream_question_ids
            ],
            "upstream_for_question": question_id,
            "question_snapshots": scoped_snapshots,
        }

    @classmethod
    def _snapshot_is_healthier(cls, candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
        candidate_metrics = cls._snapshot_health_metrics(candidate)
        baseline_metrics = cls._snapshot_health_metrics(baseline)
        candidate_key = (
            candidate_metrics["authenticity_rank"],
            candidate_metrics["completed_modules"],
            candidate_metrics["nonempty_payload_size"],
            int(candidate_metrics["has_real_trace"]),
            int(candidate_metrics["has_summary"]),
            -candidate_metrics["failed_modules"],
        )
        baseline_key = (
            baseline_metrics["authenticity_rank"],
            baseline_metrics["completed_modules"],
            baseline_metrics["nonempty_payload_size"],
            int(baseline_metrics["has_real_trace"]),
            int(baseline_metrics["has_summary"]),
            -baseline_metrics["failed_modules"],
        )
        return candidate_key > baseline_key

    @staticmethod
    def _merge_record_raw_payload(record: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(record, dict):
            return {}
        composed = record.get("composed")
        composed = composed if isinstance(composed, dict) else {}
        raw = composed.get("raw")
        raw = raw if isinstance(raw, dict) else {}

        merged: dict[str, Any] = {}
        for key in ("result", "context_updates", "execution_result"):
            payload = raw.get(key)
            if isinstance(payload, dict):
                merged.update(deepcopy(payload))
                nested_context_updates = payload.get("context_updates")
                if isinstance(nested_context_updates, dict):
                    merged.update(deepcopy(nested_context_updates))
        return merged

    @staticmethod
    def _has_meaningful_payload(value: Any) -> bool:
        if isinstance(value, dict):
            return any(NineQuestionService._has_meaningful_payload(item) for item in value.values())
        if isinstance(value, list):
            return any(NineQuestionService._has_meaningful_payload(item) for item in value)
        return value not in (None, "", [], {})

    @classmethod
    def _preserve_committed_record_sections(
        cls,
        *,
        existing: dict[str, Any],
        rebuilt: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(existing, dict):
            return rebuilt

        merged = deepcopy(rebuilt)
        existing_composed = existing.get("composed") if isinstance(existing.get("composed"), dict) else {}
        rebuilt_composed = merged.setdefault("composed", {})
        preserved_sections: list[str] = []

        for section_name in ("evidence", "inference", "trace", "summary"):
            existing_section = existing_composed.get(section_name)
            rebuilt_section = rebuilt_composed.get(section_name)
            if cls._has_meaningful_payload(existing_section) and not cls._has_meaningful_payload(rebuilt_section):
                rebuilt_composed[section_name] = deepcopy(existing_section)
                preserved_sections.append(f"composed.{section_name}")

        existing_modules = existing.get("modules") if isinstance(existing.get("modules"), dict) else {}
        rebuilt_modules = merged.setdefault("modules", {})
        stale_modules: list[str] = []
        for module_id, module_payload in existing_modules.items():
            rebuilt_module = rebuilt_modules.get(module_id)
            existing_data = module_payload.get("data") if isinstance(module_payload, dict) else None
            rebuilt_data = rebuilt_module.get("data") if isinstance(rebuilt_module, dict) else None
            if cls._has_meaningful_payload(existing_data) and not cls._has_meaningful_payload(rebuilt_data):
                rebuilt_modules[module_id] = deepcopy(module_payload)
                stale_modules.append(module_id)

        if stale_modules:
            preserved_sections.append("modules")

        if preserved_sections:
            status = merged.setdefault("status", {})
            status["preserved_sections"] = sorted(dict.fromkeys([
                *status.get("preserved_sections", []),
                *preserved_sections,
            ]))
            status["stale_modules"] = sorted(dict.fromkeys([
                *status.get("stale_modules", []),
                *stale_modules,
            ]))
            status["preservation_reason"] = status.get("preservation_reason") or "preserved_committed_sections_on_rebuild"

        return merged

    @staticmethod
    def _snapshot_module_outputs(snapshot: dict[str, Any]) -> dict[str, Any]:
        payload = snapshot.get("module_outputs")
        return deepcopy(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _snapshot_module_runs(snapshot: dict[str, Any]) -> dict[str, Any]:
        raw_runs = snapshot.get("module_runs")
        if not isinstance(raw_runs, list):
            return {}
        return {
            str(item.get("module_id") or ""): deepcopy(item)
            for item in raw_runs
            if isinstance(item, dict) and str(item.get("module_id") or "").strip()
        }

    # ------------------------------------------------------------------
    # Snapshot helpers (static — no I/O)
    # ------------------------------------------------------------------

    @staticmethod
    def get_question_snapshot_map(state: Any) -> dict[str, dict[str, Any]]:
        if isinstance(state, dict):
            snapshots = state.get("question_snapshots")
            if isinstance(snapshots, dict):
                return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
            return {}

        snapshots = getattr(state, "question_snapshots", None)
        if isinstance(snapshots, dict):
            return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
        return {}

    @classmethod
    def snapshot_has_usable_data(cls, snapshot: Any) -> bool:
        if not isinstance(snapshot, dict):
            return False

        trace_id = str(snapshot.get("trace_id") or "").strip()
        if trace_id and not trace_id.endswith(":no-trace"):
            return True

        summary = str(snapshot.get("summary") or "").strip()
        if summary:
            return True

        for key in ("context_updates", "result", "execution_result", "llm_trace_payload"):
            value = snapshot.get(key)
            if isinstance(value, dict) and value:
                return True
            if isinstance(value, list) and value:
                return True
            if isinstance(value, str) and value.strip():
                return True

        return False

    @classmethod
    def state_has_complete_question_data(cls, state: Any) -> bool:
        snapshot_map = cls.get_question_snapshot_map(state)
        if not snapshot_map:
            return False

        if isinstance(state, dict):
            snapshot_version = int(state.get("snapshot_version", 0) or 0)
        else:
            snapshot_version = int(getattr(state, "snapshot_version", 0) or 0)

        if snapshot_version < len(EXPECTED_QUESTION_IDS):
            return False
        return all(
            question_id in snapshot_map and cls.snapshot_has_usable_data(snapshot_map.get(question_id))
            for question_id in EXPECTED_QUESTION_IDS
        )

    @classmethod
    def state_has_any_question_data(cls, state: Any) -> bool:
        snapshot_map = cls.get_question_snapshot_map(state)
        if not snapshot_map:
            return False
        return any(cls.snapshot_has_usable_data(snapshot) for snapshot in snapshot_map.values())

    @staticmethod
    def state_requires_refresh(state: Any) -> bool:
        if isinstance(state, dict):
            return bool(state.get("dirty_questions") or [])
        return bool(getattr(state, "dirty_questions", []) or [])

    @classmethod
    def _dirty_expected_questions(cls, state: Any) -> list[str]:
        dirty_questions = (
            cls._normalize_dirty_questions(state.get("dirty_questions", []))
            if isinstance(state, dict)
            else cls._normalize_dirty_questions(getattr(state, "dirty_questions", []))
        )
        expected = set(EXPECTED_QUESTION_IDS)
        return [question_id for question_id in dirty_questions if question_id in expected]

    @classmethod
    def _dirty_q1_q3_questions(cls, state: Any) -> list[str]:
        q1_q3 = {"q1", "q2", "q3"}
        return [question_id for question_id in cls._dirty_expected_questions(state) if question_id in q1_q3]

    @classmethod
    def _snapshot_fingerprint(cls, snapshot_map: dict[str, dict[str, Any]]) -> tuple[tuple[str, str, int], ...]:
        fingerprint: list[tuple[str, str, int, str, str]] = []
        for question_id in EXPECTED_QUESTION_IDS:
            snapshot = snapshot_map.get(question_id) or {}
            context_updates = snapshot.get("context_updates") if isinstance(snapshot, dict) else {}
            result_payload = snapshot.get("result") if isinstance(snapshot, dict) else {}
            diagnosis = (
                context_updates.get(f"{question_id}_execution_diagnosis")
                if isinstance(context_updates, dict)
                else {}
            )
            module_runs = diagnosis.get("module_runs") if isinstance(diagnosis, dict) else []
            trace_id = str(snapshot.get("trace_id") or "")
            fingerprint.append(
                (
                    question_id,
                    trace_id,
                    len(module_runs) if isinstance(module_runs, list) else 0,
                    cls._json_fingerprint(context_updates if isinstance(context_updates, dict) else {}),
                    cls._json_fingerprint(result_payload if isinstance(result_payload, dict) else {}),
                )
            )
        return tuple(fingerprint)

    @classmethod
    def live_state_should_replace_persisted(cls, persisted_state: Any, live_state: Any) -> bool:
        live_snapshot_map = cls.get_question_snapshot_map(live_state)
        live_complete = cls.state_has_complete_question_data(live_state)
        live_has_any = cls.state_has_any_question_data(live_state)
        if not live_has_any:
            return False
        if persisted_state is None:
            return True
        persisted_complete = cls.state_has_complete_question_data(persisted_state)
        if live_complete and not persisted_complete:
            return True
        if cls.state_requires_refresh(persisted_state):
            return True

        if isinstance(live_state, dict):
            live_version = int(live_state.get("snapshot_version", 0) or 0)
        else:
            live_version = int(getattr(live_state, "snapshot_version", 0) or 0)
        if isinstance(persisted_state, dict):
            persisted_version = int(persisted_state.get("snapshot_version", 0) or 0)
        else:
            persisted_version = int(getattr(persisted_state, "snapshot_version", 0) or 0)

        def _has_healthier_snapshot_candidate() -> bool:
            persisted_snapshot_map = cls.get_question_snapshot_map(persisted_state)
            for question_id, live_snapshot in live_snapshot_map.items():
                persisted_snapshot = persisted_snapshot_map.get(question_id)
                decision = cls._should_accept_new_snapshot(persisted_snapshot, live_snapshot)
                if decision["accept_snapshot"] and (
                    persisted_snapshot is None
                    or cls._json_fingerprint(live_snapshot) != cls._json_fingerprint(persisted_snapshot)
                ):
                    return True
            return False

        if live_version > persisted_version:
            return _has_healthier_snapshot_candidate()

        persisted_snapshot_map = cls.get_question_snapshot_map(persisted_state)
        if cls._snapshot_fingerprint(live_snapshot_map) == cls._snapshot_fingerprint(persisted_snapshot_map):
            return False

        if live_complete:
            return _has_healthier_snapshot_candidate()

        live_updated_at = str(
            live_state.get("last_updated_at", "")
            if isinstance(live_state, dict)
            else getattr(live_state, "last_updated_at", "")
        )
        persisted_updated_at = str(
            persisted_state.get("updated_at", persisted_state.get("last_updated_at", ""))
            if isinstance(persisted_state, dict)
            else getattr(persisted_state, "updated_at", getattr(persisted_state, "last_updated_at", ""))
        )
        return bool(live_updated_at and live_updated_at >= persisted_updated_at and _has_healthier_snapshot_candidate())

    @staticmethod
    def _record_has_matching_diagnostic_modules(question_id: str, record: dict[str, Any], snapshot: dict[str, Any]) -> bool:
        if not isinstance(record, dict) or not isinstance(snapshot, dict):
            return False

        raw = ((record.get("composed") or {}).get("raw") or {}) if isinstance(record.get("composed"), dict) else {}
        record_context_updates = raw.get("context_updates") if isinstance(raw, dict) else {}
        record_diagnosis = (
            record_context_updates.get(f"{question_id}_execution_diagnosis")
            if isinstance(record_context_updates, dict)
            else {}
        )
        snapshot_context_updates = snapshot.get("context_updates") if isinstance(snapshot.get("context_updates"), dict) else {}
        snapshot_diagnosis = snapshot_context_updates.get(f"{question_id}_execution_diagnosis") or {}

        record_runs = record_diagnosis.get("module_runs") if isinstance(record_diagnosis, dict) else []
        snapshot_runs = snapshot_diagnosis.get("module_runs") if isinstance(snapshot_diagnosis, dict) else []
        if not isinstance(snapshot_runs, list):
            return True
        if not isinstance(record_runs, list):
            return False
        record_ids = [str(item.get("module_id") or "") for item in record_runs if isinstance(item, dict)]
        snapshot_ids = [str(item.get("module_id") or "") for item in snapshot_runs if isinstance(item, dict)]
        return record_ids == snapshot_ids

    @staticmethod
    def _record_matches_current_composed_schema(record: dict[str, Any]) -> bool:
        if not isinstance(record, dict):
            return False
        top_level_version = int(record.get("composed_schema_version") or 0)
        status = record.get("status")
        status_version = int((status or {}).get("composed_schema_version") or 0) if isinstance(status, dict) else 0
        return max(top_level_version, status_version) >= COMPOSED_RECORD_SCHEMA_VERSION

    @staticmethod
    def _json_fingerprint(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return repr(value)

    @classmethod
    def _record_matches_snapshot_projection(
        cls,
        question_id: str,
        record: dict[str, Any],
        snapshot: dict[str, Any],
        snapshot_map: dict[str, dict[str, Any]] = None,
    ) -> bool:
        if not isinstance(record, dict) or not isinstance(snapshot, dict):
            return False

        composed = record.get("composed")
        composed = composed if isinstance(composed, dict) else {}
        raw = composed.get("raw")
        raw = raw if isinstance(raw, dict) else {}

        projected_record = build_question_record(question_id, snapshot, snapshot_map or {question_id: snapshot})
        projected_composed = projected_record.get("composed")
        projected_composed = projected_composed if isinstance(projected_composed, dict) else {}
        projected_raw = projected_composed.get("raw")
        projected_raw = projected_raw if isinstance(projected_raw, dict) else {}

        record_trace_id = str(raw.get("trace_id") or "")
        projected_trace_id = str(projected_raw.get("trace_id") or "")
        if record_trace_id != projected_trace_id:
            return False

        record_result = raw.get("result")
        projected_result = projected_raw.get("result")
        if cls._json_fingerprint(record_result) != cls._json_fingerprint(projected_result):
            return False

        record_context_updates = raw.get("context_updates")
        projected_context_updates = projected_raw.get("context_updates")
        if cls._json_fingerprint(record_context_updates) != cls._json_fingerprint(projected_context_updates):
            return False

        return cls._record_has_matching_diagnostic_modules(question_id, record, snapshot)

    # ------------------------------------------------------------------
    # Snapshot merge helpers (static — no I/O)
    # ------------------------------------------------------------------

    @classmethod
    def _should_accept_new_snapshot(
        cls,
        existing: dict[str, Any],
        new: dict[str, Any],
    ) -> dict[str, Any]:
        """Decide whether *new* should replace *existing* in the persisted store.

        Fail-closed rules:
        - No existing data → always accept new.
        - New has a real trace_id, existing has none → accept.
        - New has a summary, existing has none → accept.
        - Existing has a real summary/trace and new is empty/failed → REJECT.
        - New trace ends with ':no-trace' while existing trace is real → REJECT.

        This enforces the nine-questions contract: partial failure must never
        overwrite previously successful answers.
        """
        if not existing:
            return {
                "accept_snapshot": True,
                "merge_diagnostics_only": False,
                "preserve_previous_success": False,
                "reason": "no_existing_snapshot",
            }

        new_trace = str(new.get("trace_id") or "").strip()
        existing_trace = str(existing.get("trace_id") or "").strip()
        new_summary = str(new.get("summary") or "").strip()
        existing_summary = str(existing.get("summary") or "").strip()

        # Existing is a real result; new is empty or still "no-trace" → protect old data
        if existing_summary and not new_summary:
            return {
                "accept_snapshot": False,
                "merge_diagnostics_only": True,
                "preserve_previous_success": True,
                "reason": "new_summary_missing",
            }
        if existing_trace and not existing_trace.endswith(":no-trace") and new_trace.endswith(":no-trace"):
            return {
                "accept_snapshot": False,
                "merge_diagnostics_only": True,
                "preserve_previous_success": True,
                "reason": "new_trace_degraded",
            }
        if cls._snapshot_is_intrinsically_qualified(existing) and not cls._snapshot_is_intrinsically_qualified(new):
            return {
                "accept_snapshot": False,
                "merge_diagnostics_only": True,
                "preserve_previous_success": True,
                "reason": "existing_snapshot_qualified_new_snapshot_unqualified",
            }
        if cls._snapshot_is_intrinsically_qualified(existing) and cls._snapshot_is_intrinsically_qualified(new):
            existing_metrics = cls._snapshot_health_metrics(existing)
            new_metrics = cls._snapshot_health_metrics(new)
            if (
                new_metrics["authenticity_rank"] >= existing_metrics["authenticity_rank"]
                and new_metrics["completed_modules"] >= existing_metrics["completed_modules"]
                and new_metrics["failed_modules"] <= existing_metrics["failed_modules"]
                and new_metrics["has_real_trace"]
                and new_metrics["has_summary"]
            ):
                return {
                    "accept_snapshot": True,
                    "merge_diagnostics_only": False,
                    "preserve_previous_success": False,
                    "reason": "qualified_rerun_accepted",
                }
        if cls._snapshot_is_healthier(existing, new):
            return {
                "accept_snapshot": False,
                "merge_diagnostics_only": True,
                "preserve_previous_success": True,
                "reason": "existing_snapshot_healthier",
            }
        return {
            "accept_snapshot": True,
            "merge_diagnostics_only": False,
            "preserve_previous_success": False,
            "reason": "new_snapshot_accepted",
        }

    @staticmethod
    def _merge_diagnostic_only(
        existing: dict[str, Any],
        new: dict[str, Any],
    ) -> dict[str, Any]:
        """When *new* is rejected by _should_accept_new_snapshot, still forward
        the execution-diagnosis module_runs from *new* into *existing* so the UI
        can show that a re-run was attempted and which modules ran.

        Rejected diagnostics are stored under '*_rejected_execution_diagnosis';
        canonical '*_execution_diagnosis' keys are not touched, because latest
        qualification gates must continue to see the committed success.
        """
        merged = deepcopy(existing)
        new_context_updates = new.get("context_updates")
        if not isinstance(new_context_updates, dict):
            return merged
        existing_context_updates = merged.setdefault("context_updates", {})
        for key, value in new_context_updates.items():
            if key.endswith("_execution_diagnosis"):
                existing_context_updates[NineQuestionService._rejected_diagnosis_key(key)] = deepcopy(value)
        return merged

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    async def persist_kernel_state(self, state: Any) -> None:
        """Persist only latest qualified question snapshots to SQLite."""
        snapshot_map = self.get_question_snapshot_map(state)
        if not snapshot_map:
            return

        try:
            existing_state = await self._state_manager.get_state(_NQ_STATE_KEY)
            existing_snapshot_map = self.get_question_snapshot_map(existing_state)
        except ValueError:
            existing_snapshot_map = {}
            await self._state_manager.bootstrap_state(_NQ_STATE_KEY)

        merged_snapshot_map: dict[str, Any] = dict(existing_snapshot_map)
        accepted_question_ids: list[str] = []
        history_updates: dict[str, list[dict[str, Any]]] = {}
        for question_id, new_snapshot in snapshot_map.items():
            current_snapshot = existing_snapshot_map.get(question_id) or {}
            qualified_snapshot = self._snapshot_is_intrinsically_qualified(new_snapshot)
            if not qualified_snapshot:
                logger.warning(
                    "[nine-questions] skip unqualified snapshot persist question=%s",
                    question_id,
                )
                continue
            history_entry = await self._persist_question_history_version(
                question_id=question_id,
                current_snapshot=current_snapshot,
                reason="qualified_snapshot_persisted",
            )
            if history_entry:
                history_updates.setdefault(question_id, []).append(history_entry)
            merged_snapshot_map[question_id] = self._append_question_history_version(
                question_id=question_id,
                current_snapshot=current_snapshot,
                new_snapshot=new_snapshot,
                reason="qualified_snapshot_persisted",
            )
            accepted_question_ids.append(question_id)

        if not accepted_question_ids:
            return

        merged_snapshot_map = self._normalize_snapshot_map_metadata(
            merged_snapshot_map,
            touch_updated_at=True,
        )

        if isinstance(state, dict):
            snapshot_version = int(state.get("snapshot_version", len(merged_snapshot_map)))
            last_refresh_reason = state.get("last_refresh_reason")
            current_dirty = self._normalize_dirty_questions(state.get("dirty_questions"))
        else:
            snapshot_version = int(getattr(state, "snapshot_version", len(merged_snapshot_map)))
            last_refresh_reason = getattr(state, "last_refresh_reason", None)
            current_dirty = self._normalize_dirty_questions(getattr(state, "dirty_questions", []))

        accepted_set = set(accepted_question_ids)
        dirty_questions = [item for item in current_dirty if item not in accepted_set]

        await self._state_manager.update_state(
            _NQ_STATE_KEY,
            question_snapshots=merged_snapshot_map,
            snapshot_version=snapshot_version,
            last_refresh_reason=last_refresh_reason,
            dirty_questions=dirty_questions,
            **({"question_snapshots_history": history_updates} if history_updates else {}),
        )

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    async def get_state(self) -> Any:
        """Return the authoritative nine-question baseline state."""
        try:
            return await self._state_manager.get_state(_NQ_STATE_KEY)
        except ValueError:
            return await self._state_manager.bootstrap_state(_NQ_STATE_KEY)

    async def get_state_metadata(self) -> dict[str, Any]:
        get_metadata = getattr(self._state_manager, "get_state_metadata", None)
        if callable(get_metadata):
            metadata = await get_metadata(_NQ_STATE_KEY)
            if isinstance(metadata, dict):
                return metadata
        state = await self.get_state()
        if isinstance(state, dict):
            return {
                "version": state.get("version", 1),
                "revision": state.get("revision", 0),
                "dirty_questions": state.get("dirty_questions", []),
                "last_refresh_reason": state.get("last_refresh_reason"),
                "snapshot_version": state.get("snapshot_version", 0),
                "updated_at": state.get("last_updated_at") or state.get("updated_at"),
            }
        return {
            "version": getattr(state, "version", 1),
            "revision": getattr(state, "revision", 0),
            "dirty_questions": getattr(state, "dirty_questions", []),
            "last_refresh_reason": getattr(state, "last_refresh_reason", None),
            "snapshot_version": getattr(state, "snapshot_version", 0),
            "updated_at": getattr(state, "updated_at", None),
        }

    async def get_snapshot_map(self) -> dict[str, dict[str, Any]]:
        return self.get_question_snapshot_map(await self.get_state())

    async def get_latest_question_snapshots(self, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        get_snapshots = getattr(self._state_manager, "get_question_snapshots", None)
        if callable(get_snapshots):
            snapshots = await get_snapshots(_NQ_STATE_KEY, question_ids)
            if isinstance(snapshots, dict):
                return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
        raise RuntimeError("Nine-question snapshots must be read from SQLite question tables")

    async def get_latest_question_summary_rows(self, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        get_rows = getattr(self._state_manager, "get_question_summary_rows", None)
        if callable(get_rows):
            rows = await get_rows(_NQ_STATE_KEY, question_ids)
            if isinstance(rows, dict):
                return {str(key): value for key, value in rows.items() if isinstance(value, dict)}

        snapshots = await self.get_latest_question_snapshots(question_ids)
        rows: dict[str, dict[str, Any]] = {}
        for question_id, snapshot in snapshots.items():
            if not isinstance(snapshot, dict):
                continue
            rows[question_id] = {
                "question_id": question_id,
                "tool_id": snapshot.get("tool_id"),
                "summary": snapshot.get("summary"),
                "confidence": snapshot.get("confidence"),
                "trace_id": snapshot.get("trace_id"),
                "timestamp": snapshot.get("timestamp") or snapshot.get("updated_at"),
                "cache_status": snapshot.get("cache_status"),
                "provider_name": snapshot.get("provider_name"),
                "mounted_plugins": deepcopy(snapshot.get("mounted_plugins")) if isinstance(snapshot.get("mounted_plugins"), list) else [],
            }
        return rows

    async def query_latest_question_snapshot(self, question_id: str) -> dict[str, Any]:
        """Query only the current canonical snapshot for one question."""
        snapshot = await self.get_question_snapshot(question_id)
        return deepcopy(snapshot) if isinstance(snapshot, dict) else {}

    async def query_question_snapshot_history(
        self,
        question_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query only append-only historical snapshots for one question."""
        get_history = getattr(self._state_manager, "get_question_snapshot_history", None)
        if not callable(get_history):
            raise RuntimeError("Nine-question snapshot history store is unavailable")
        history = await get_history(_NQ_STATE_KEY, question_id, limit=limit)
        return [deepcopy(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []

    @staticmethod
    def _json_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return deepcopy(value)
        if value in (None, ""):
            return {}
        try:
            loaded = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def sqlite_db_path(self) -> Path:
        store = getattr(self._state_manager, "_store", None)
        db_path = getattr(store, "db_path", None) or getattr(self._state_manager, "db_path", None)
        if not db_path:
            raise RuntimeError("Nine-question query API requires SQLite nine-question state store access")
        return Path(db_path)

    def _q2_sqlite_db_path(self) -> Path:
        return self.sqlite_db_path()

    def _read_q2_snapshot_table_row_sync(self) -> dict[str, Any]:
        """Read the Q2 row directly from nine_question_q2_snapshots.

        Q2 query APIs are intentionally table-authoritative. They do not rebuild
        Q2 from legacy composed evidence/inference logic.
        """
        db_path = self._q2_sqlite_db_path()
        if not db_path.exists():
            return {}
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f"""
                    SELECT llm_output_json, llm_trace_json, updated_at
                    FROM {_Q2_SNAPSHOT_TABLE}
                    WHERE session_id = ?
                    """,
                    (_NQ_STATE_KEY,),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if _Q2_SNAPSHOT_TABLE in str(exc) or "no such table" in str(exc):
                return {}
            raise
        if row is None:
            return {}

        llm_output = self._json_dict(row["llm_output_json"])
        llm_trace = self._json_dict(row["llm_trace_json"])
        trace_id = str(
            llm_trace.get("trace_id")
            or ""
        ).strip()
        timestamp = str(
            row["updated_at"]
            or ""
        ).strip()
        return {
            "question_id": "q2",
            "source_table": _Q2_SNAPSHOT_TABLE,
            "trace_id": trace_id,
            "timestamp": timestamp,
            "llm_output": llm_output,
            "llm_trace_payload": llm_trace,
            "updated_at": str(row["updated_at"] or ""),
        }

    async def _read_q2_snapshot_table_row(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._read_q2_snapshot_table_row_sync)

    @staticmethod
    def _q2_first_scoped_trace(trace_payload: dict[str, Any], scope: str) -> dict[str, Any]:
        if not isinstance(trace_payload, dict):
            return {}

        trace_key = (
            "internal_tool_llm_trace_payload"
            if scope == "internal_tools"
            else "external_tool_llm_trace_payload"
        )
        direct = trace_payload.get(trace_key)
        if isinstance(direct, dict) and direct:
            scoped = deepcopy(direct)
        else:
            scoped = {}
            invocations = trace_payload.get("invocations")
            if isinstance(invocations, list):
                for item in invocations:
                    if isinstance(item, dict) and item.get("asset_scope") == scope:
                        scoped = deepcopy(item)
                        break
        if not scoped:
            return {}

        scoped["asset_scope"] = scope
        scoped.pop("invocations", None)
        input_payload = {
            key: deepcopy(scoped.get(key))
            for key in (
                "provider_name",
                "model",
                "system_prompt",
                "prompt",
                "context_data",
                "source_module",
                "invocation_phase",
                "question_driver_refs",
            )
            if scoped.get(key) not in (None, "", [], {})
        }
        scoped["input"] = input_payload
        return scoped

    @staticmethod
    def _q2_rooted_llm_output(value: Any, root_key: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        rooted = value.get(root_key)
        if isinstance(rooted, dict):
            return {root_key: deepcopy(rooted)}
        return {root_key: deepcopy(value)}

    @classmethod
    def _q2_scoped_llm_output(
        cls,
        table_row: dict[str, Any],
        *,
        scope: str,
        root_key: str,
        inventory_key: str,
    ) -> dict[str, Any]:
        llm_output = table_row.get("llm_output")
        if isinstance(llm_output, dict):
            rooted = cls._q2_rooted_llm_output(llm_output.get(inventory_key), root_key)
            if rooted:
                return rooted
        return {root_key: {}}

    @staticmethod
    def _q2_token_usage(value: Any) -> dict[str, int]:
        value = value if isinstance(value, dict) else {}
        return {
            "input_tokens": int(value.get("input_tokens") or 0),
            "output_tokens": int(value.get("output_tokens") or 0),
            "total_tokens": int(value.get("total_tokens") or 0),
        }

    @classmethod
    def _q2_scoped_llm_exchange(
        cls,
        table_row: dict[str, Any],
        *,
        scope: str,
        root_key: str,
        inventory_key: str,
    ) -> dict[str, Any]:
        trace_payload = table_row.get("llm_trace_payload")
        trace_payload = trace_payload if isinstance(trace_payload, dict) else {}
        scoped_trace = cls._q2_first_scoped_trace(trace_payload, scope)
        input_trace = scoped_trace.get("input") if isinstance(scoped_trace.get("input"), dict) else {}
        token_usage = cls._q2_token_usage(scoped_trace.get("token_usage"))
        input_llm = {
            key: deepcopy(value)
            for key, value in {
                "system_prompt": scoped_trace.get("system_prompt") or input_trace.get("system_prompt"),
                "prompt": scoped_trace.get("prompt") or input_trace.get("prompt"),
                "context_data": scoped_trace.get("context_data") or input_trace.get("context_data"),
            }.items()
            if value not in (None, "", [], {})
        }
        output_llm = cls._q2_scoped_llm_output(
            table_row,
            scope=scope,
            root_key=root_key,
            inventory_key=inventory_key,
        )
        return {
            "provider_name": str(scoped_trace.get("provider_name") or input_trace.get("provider_name") or ""),
            "token_usage": token_usage,
            "input_llm": input_llm,
            "output_llm": output_llm,
        }

    @classmethod
    def _project_q2_llm_io(cls, table_row: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(table_row, dict) or not table_row:
            return {
                "question_id": "q2",
                "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "internal_tool_llm": {
                    "provider_name": "",
                    "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    "input_llm": {},
                    "output_llm": {"InternalAssetInventory": {}},
                },
                "external_tool_llm": {
                    "provider_name": "",
                    "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    "input_llm": {},
                    "output_llm": {"ExternalAssetInventory": {}},
                },
            }
        internal_exchange = cls._q2_scoped_llm_exchange(
            table_row,
            scope="internal_tools",
            root_key="InternalAssetInventory",
            inventory_key="q2_internal_tool_asset_inventory",
        )
        external_exchange = cls._q2_scoped_llm_exchange(
            table_row,
            scope="external_tools",
            root_key="ExternalAssetInventory",
            inventory_key="q2_external_tool_asset_inventory",
        )
        internal_tokens = cls._q2_token_usage(internal_exchange.get("token_usage"))
        external_tokens = cls._q2_token_usage(external_exchange.get("token_usage"))
        return {
            "question_id": "q2",
            "token_usage": {
                "input_tokens": internal_tokens["input_tokens"] + external_tokens["input_tokens"],
                "output_tokens": internal_tokens["output_tokens"] + external_tokens["output_tokens"],
                "total_tokens": internal_tokens["total_tokens"] + external_tokens["total_tokens"],
            },
            "internal_tool_llm": internal_exchange,
            "external_tool_llm": external_exchange,
        }

    async def _get_q2_llm_io_projection(self) -> dict[str, Any]:
        return self._project_q2_llm_io(await self._read_q2_snapshot_table_row())

    async def get_q2_llm_trace(self) -> dict[str, Any]:
        return await self._get_q2_llm_io_projection()

    async def get_question_snapshot(self, question_id: str) -> dict[str, Any]:
        return (await self.get_latest_question_snapshots([question_id])).get(question_id)

    async def load_authoritative_question_context(self, question_ids: list[str]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for question_id in question_ids:
            merged.update(self._merge_record_raw_payload(await self.get_question_record(question_id)))
        return merged

    async def load_authoritative_question_bundle(self, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        bundle: dict[str, dict[str, Any]] = {}
        for question_id in question_ids:
            bundle[question_id] = self._merge_record_raw_payload(await self.get_question_record(question_id))
        return bundle

    async def get_flat_dependency_context(self, *, upto_question_id: str) -> dict[str, Any]:
        snapshot_map = await self.get_snapshot_map()
        return _query_build_flat_upstream_context(upto_question_id, snapshot_map)

    async def get_question_record(self, question_id: str) -> dict[str, Any]:
        snapshot_map = await self.get_latest_question_snapshots([question_id])
        snapshot = snapshot_map.get(question_id)
        if not self.snapshot_has_usable_data(snapshot):
            return {"status": {}, "modules": {}, "composed": {}}

        return build_question_record(
            question_id,
            snapshot,
            snapshot_map,
            module_payload_overrides=self._snapshot_module_outputs(snapshot),
            module_run_overrides=self._snapshot_module_runs(snapshot),
        )

    async def get_question_records(self, question_ids: list[str]) -> dict[str, dict[str, Any]]:
        snapshot_map = await self.get_latest_question_snapshots(question_ids)
        records: dict[str, dict[str, Any]] = {}
        for question_id in question_ids:
            snapshot = snapshot_map.get(question_id)
            if not self.snapshot_has_usable_data(snapshot):
                records[question_id] = {"status": {}, "modules": {}, "composed": {}}
                continue
            records[question_id] = build_question_record(
                question_id,
                snapshot,
                snapshot_map,
                module_payload_overrides=self._snapshot_module_outputs(snapshot),
                module_run_overrides=self._snapshot_module_runs(snapshot),
            )
        return records

    async def get_question_summary(self, question_id: str) -> dict[str, Any]:
        return (await self.get_question_record(question_id)).get("composed", {}).get("summary", {})

    async def get_question_evidence(self, question_id: str) -> dict[str, Any]:
        return (await self.get_question_record(question_id)).get("composed", {}).get("evidence", {})

    async def get_question_inference(self, question_id: str) -> dict[str, Any]:
        return (await self.get_question_record(question_id)).get("composed", {}).get("inference", {})

    async def get_question_trace(self, question_id: str) -> dict[str, Any]:
        return (await self.get_question_record(question_id)).get("composed", {}).get("trace", {})

    async def get_question_raw(self, question_id: str) -> dict[str, Any]:
        return (await self.get_question_record(question_id)).get("composed", {}).get("raw", {})

    async def get_q2_asset_statistics(
        self,
        *,
        cli_service: Any = None,
        mcp_service: Any = None,
        agent_service: Any = None,
        external_connector_service: Any = None,
    ) -> dict[str, Any]:
        get_outputs = getattr(self._state_manager, "get_question_module_outputs", None)
        module_outputs = await get_outputs(_NQ_STATE_KEY, "q2") if callable(get_outputs) else {}
        module_outputs = module_outputs if isinstance(module_outputs, dict) else {}

        internal_output = module_outputs.get("q2_internal_asset_counts")
        external_output = module_outputs.get("q2_external_asset_counts")
        internal_data = self._module_output_data(internal_output)
        external_data = self._module_output_data(external_output)

        internal_plugin_count = self._non_negative_int(internal_data.get("internal_plugin_count"))
        cli_count = self._first_available_count(
            self._count_service_list(cli_service, "list_tools"),
            external_data.get("cli_count"),
        )
        mcp_count = self._first_available_count(
            self._count_mcp_servers(mcp_service),
            external_data.get("mcp_count"),
        )
        agent_count = self._first_available_count(
            self._count_agents(agent_service),
            external_data.get("agent_count"),
        )
        external_service_count = self._first_available_count(
            self._count_external_connectors(external_connector_service),
            external_data.get("external_service_count"),
        )
        source_table = (
            "runtime_service_registries"
            if any(service is not None for service in (cli_service, mcp_service, agent_service, external_connector_service))
            else "nine_question_module_outputs"
        )

        return {
            "question_id": "q2",
            "source_table": source_table,
            "internal_plugin_count": internal_plugin_count,
            "cli_count": cli_count,
            "mcp_count": mcp_count,
            "agent_count": agent_count,
            "external_service_count": external_service_count,
            "total_count": internal_plugin_count + cli_count + mcp_count + agent_count + external_service_count,
        }

    @staticmethod
    def _module_output_data(output: Any) -> dict[str, Any]:
        if not isinstance(output, dict):
            return {}
        data = output.get("data")
        return data if isinstance(data, dict) else {}

    @classmethod
    def _first_available_count(cls, primary: int | None, fallback: Any) -> int:
        if primary is not None:
            return primary
        return cls._non_negative_int(fallback)

    @staticmethod
    def _count_service_list(service: Any, method_name: str) -> int | None:
        if service is None:
            return None
        method = getattr(service, method_name, None)
        if not callable(method):
            return None
        try:
            rows = method()
        except Exception:
            logger.exception("[Q2] failed to count runtime service list method=%s", method_name)
            return None
        if isinstance(rows, dict):
            return len(rows)
        if isinstance(rows, (list, tuple, set)):
            return len(rows)
        return None

    @classmethod
    def _count_mcp_servers(cls, service: Any) -> int | None:
        if service is None:
            return None
        if callable(getattr(service, "list_servers", None)):
            return cls._count_service_list(service, "list_servers")
        try:
            from zentex.mcp.service import resolve_service as resolve_mcp_service

            service = resolve_mcp_service(service)
        except Exception:
            logger.exception("[Q2] failed to resolve MCP service for asset statistics")
        return cls._count_service_list(service, "list_servers")

    @classmethod
    def _count_external_connectors(cls, service: Any) -> int | None:
        if service is None:
            return None
        if callable(getattr(service, "list_connectors", None)):
            return cls._count_service_list(service, "list_connectors")
        try:
            from zentex.external_connectors.service import resolve_service as resolve_external_connector_service

            service = resolve_external_connector_service(service)
        except Exception:
            logger.exception("[Q2] failed to resolve external connector service for asset statistics")
        return cls._count_service_list(service, "list_connectors")

    @classmethod
    def _count_agents(cls, service: Any) -> int | None:
        if service is None:
            return None
        manager = getattr(service, "manager", None)
        manager_count = cls._count_service_list(manager, "list_assets")
        if manager_count is not None:
            return manager_count
        for method_name in ("list_active_agents", "list_agents"):
            count = cls._count_service_list(service, method_name)
            if count is not None:
                return count
        return None

    @staticmethod
    def _non_negative_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    async def get_question_modules(self, question_id: str) -> dict[str, Any]:
        record = await self.get_question_record(question_id)
        get_runs = getattr(self._state_manager, "get_question_module_runs", None)
        get_outputs = getattr(self._state_manager, "get_question_module_outputs", None)
        module_runs = await get_runs(_NQ_STATE_KEY, question_id) if callable(get_runs) else []
        module_outputs = await get_outputs(_NQ_STATE_KEY, question_id) if callable(get_outputs) else {}
        run_overrides = {
            str(item.get("module_id")): item
            for item in module_runs
            if isinstance(item, dict) and str(item.get("module_id") or "").strip()
        }
        output_overrides = {
            str(module_id): output
            for module_id, output in module_outputs.items()
            if isinstance(output, dict)
        } if isinstance(module_outputs, dict) else {}
        if run_overrides or output_overrides:
            snapshot = await self.get_question_snapshot(question_id)
            snapshot = snapshot if isinstance(snapshot, dict) and self.snapshot_has_usable_data(snapshot) else {
                "context_updates": {
                    f"{question_id}_execution_diagnosis": {
                        "module_runs": list(run_overrides.values()),
                    }
                }
            }
            record = build_question_record(
                question_id,
                snapshot,
                {question_id: snapshot},
                module_payload_overrides=output_overrides,
                module_run_overrides=run_overrides,
            )
        return {
            "question_id": question_id,
            "status": record.get("status", {}),
            "modules": record.get("modules", {}),
            "recovery_plan": record.get("recovery_plan", {}),
        }

    async def persist_question_snapshot_patch(
        self,
        question_id: str,
        patch: dict[str, Any],
        *,
        refresh_reason: Optional[str] = None,
    ) -> dict[str, Any]:
        state = await self.get_state()
        snapshot_map = self.get_question_snapshot_map(state)
        current_snapshot = snapshot_map.get(question_id)
        if not isinstance(current_snapshot, dict):
            try:
                latest_snapshot_map = await self.get_latest_question_snapshots([question_id])
            except Exception:
                latest_snapshot_map = {}
            latest_snapshot = latest_snapshot_map.get(question_id) if isinstance(latest_snapshot_map, dict) else None
            if isinstance(latest_snapshot, dict):
                current_snapshot = latest_snapshot
                snapshot_map[question_id] = deepcopy(latest_snapshot)
        if question_id == "q3":
            patch = self._prune_q3_snapshot(patch)
            if isinstance(current_snapshot, dict):
                current_snapshot = self._prune_q3_snapshot(current_snapshot)
                snapshot_map[question_id] = deepcopy(current_snapshot)
        if not isinstance(current_snapshot, dict):
            merged_snapshot = self._append_question_history_version(
                question_id=question_id,
                current_snapshot=patch,
                new_snapshot=patch,
                reason=refresh_reason or "initial_committed_snapshot",
            )
            snapshot_map[question_id] = merged_snapshot
            snapshot_map = self._normalize_snapshot_map_metadata(
                snapshot_map,
                touch_updated_at=False,
            )
            snapshot_map[question_id] = self._normalize_snapshot_metadata(
                snapshot_map[question_id],
                now_iso=self._now_iso(),
                touch_updated_at=True,
            )

            current_dirty = (
                state.get("dirty_questions", [])
                if isinstance(state, dict)
                else getattr(state, "dirty_questions", [])
            )
            dirty_questions = self._normalize_dirty_questions(
                [item for item in current_dirty if str(item).strip() != question_id]
            )
            snapshot_version = (
                int(state.get("snapshot_version", len(snapshot_map)))
                if isinstance(state, dict)
                else int(getattr(state, "snapshot_version", len(snapshot_map)))
            )
            await self._state_manager.update_state(
                _NQ_STATE_KEY,
                question_snapshots=snapshot_map,
                snapshot_version=snapshot_version,
                dirty_questions=dirty_questions,
                last_refresh_reason=refresh_reason,
            )
            return merged_snapshot

        decision = self._should_accept_new_snapshot(current_snapshot, patch)
        if decision["accept_snapshot"]:
            merged_snapshot = self._merge_snapshot_patch(current_snapshot, patch)
        else:
            merged_snapshot = self._merge_diagnostic_only(current_snapshot, patch)
        history_reason = str(decision.get("reason") or refresh_reason or "question_snapshot_patch")
        history_entry = await self._persist_question_history_version(
            question_id=question_id,
            current_snapshot=current_snapshot,
            reason=history_reason,
        )
        merged_snapshot = self._append_question_history_version(
            question_id=question_id,
            current_snapshot=current_snapshot,
            new_snapshot=merged_snapshot,
            reason=history_reason,
        )
        snapshot_map[question_id] = merged_snapshot
        snapshot_map = self._normalize_snapshot_map_metadata(
            snapshot_map,
            touch_updated_at=False,
        )
        snapshot_map[question_id] = self._normalize_snapshot_metadata(
            snapshot_map[question_id],
            now_iso=self._now_iso(),
            touch_updated_at=True,
        )

        current_dirty = (
            state.get("dirty_questions", [])
            if isinstance(state, dict)
            else getattr(state, "dirty_questions", [])
        )
        dirty_questions = self._normalize_dirty_questions(
            [item for item in current_dirty if str(item).strip() != question_id]
        )
        snapshot_version = (
            int(state.get("snapshot_version", len(snapshot_map)))
            if isinstance(state, dict)
            else int(getattr(state, "snapshot_version", len(snapshot_map)))
        )
        await self._state_manager.update_state(
            _NQ_STATE_KEY,
            question_snapshots=snapshot_map,
            snapshot_version=snapshot_version,
            dirty_questions=dirty_questions,
            last_refresh_reason=refresh_reason,
            **self._history_update_payload(question_id, history_entry),
        )
        return merged_snapshot

    async def persist_question_module_run(
        self,
        question_id: str,
        module_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if question_id == "q3":
            return await self.rebuild_question_record(question_id)
        state = await self.get_state()
        snapshot_map = self.get_question_snapshot_map(state)
        snapshot = deepcopy(snapshot_map.get(question_id) or {})
        current_runs = snapshot.get("module_runs")
        runs = deepcopy(current_runs) if isinstance(current_runs, list) else []
        runs = [item for item in runs if str(item.get("module_id") or "") != module_id]
        runs.append(deepcopy(payload))
        snapshot["module_runs"] = runs
        snapshot_map[question_id] = snapshot
        snapshot_map = self._normalize_snapshot_map_metadata(
            snapshot_map,
            touch_updated_at=False,
        )
        snapshot_map[question_id] = self._normalize_snapshot_metadata(
            snapshot_map[question_id],
            now_iso=self._now_iso(),
            touch_updated_at=True,
        )
        await self._state_manager.update_state(
            _NQ_STATE_KEY,
            question_snapshots=snapshot_map,
            snapshot_version=int(state.get("snapshot_version", len(snapshot_map))) if isinstance(state, dict) else len(snapshot_map),
            dirty_questions=self._normalize_dirty_questions(state.get("dirty_questions", [])) if isinstance(state, dict) else [],
            last_refresh_reason=f"module_run:{question_id}:{module_id}",
        )
        return await self.rebuild_question_record(question_id)

    async def persist_question_module_output(
        self,
        question_id: str,
        module_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if question_id == "q3":
            return await self.rebuild_question_record(question_id)
        state = await self.get_state()
        snapshot_map = self.get_question_snapshot_map(state)
        snapshot = deepcopy(snapshot_map.get(question_id) or {})
        current_outputs = snapshot.get("module_outputs")
        outputs = deepcopy(current_outputs) if isinstance(current_outputs, dict) else {}
        existing = outputs.get(module_id)
        incoming_data = payload.get("data") if isinstance(payload, dict) else None
        existing_status = str((existing or {}).get("status") or "")
        if existing_status in {"completed", "ready"} and incoming_data in (None, "", [], {}):
            merged_payload = deepcopy(existing) if isinstance(existing, dict) else {}
            merged_payload.update({k: deepcopy(v) for k, v in payload.items() if k != "data"})
            payload = merged_payload
        outputs[module_id] = deepcopy(payload)
        snapshot["module_outputs"] = outputs
        snapshot_map[question_id] = snapshot
        snapshot_map = self._normalize_snapshot_map_metadata(
            snapshot_map,
            touch_updated_at=False,
        )
        snapshot_map[question_id] = self._normalize_snapshot_metadata(
            snapshot_map[question_id],
            now_iso=self._now_iso(),
            touch_updated_at=True,
        )
        await self._state_manager.update_state(
            _NQ_STATE_KEY,
            question_snapshots=snapshot_map,
            snapshot_version=int(state.get("snapshot_version", len(snapshot_map))) if isinstance(state, dict) else len(snapshot_map),
            dirty_questions=self._normalize_dirty_questions(state.get("dirty_questions", [])) if isinstance(state, dict) else [],
            last_refresh_reason=f"module_output:{question_id}:{module_id}",
        )
        return await self.rebuild_question_record(question_id)

    async def get_question_module_outputs(self, question_id: str) -> dict[str, Any]:
        snapshot = (await self.get_snapshot_map()).get(question_id) or {}
        return self._snapshot_module_outputs(snapshot)

    async def delete_question_module_output(self, question_id: str, module_id: str) -> dict[str, Any]:
        state = await self.get_state()
        snapshot_map = self.get_question_snapshot_map(state)
        snapshot = deepcopy(snapshot_map.get(question_id) or {})
        current_outputs = snapshot.get("module_outputs")
        outputs = deepcopy(current_outputs) if isinstance(current_outputs, dict) else {}
        outputs.pop(module_id, None)
        snapshot["module_outputs"] = outputs
        snapshot_map[question_id] = snapshot
        snapshot_map = self._normalize_snapshot_map_metadata(
            snapshot_map,
            touch_updated_at=False,
        )
        snapshot_map[question_id] = self._normalize_snapshot_metadata(
            snapshot_map[question_id],
            now_iso=self._now_iso(),
            touch_updated_at=True,
        )
        await self._state_manager.update_state(
            _NQ_STATE_KEY,
            question_snapshots=snapshot_map,
            snapshot_version=int(state.get("snapshot_version", len(snapshot_map))) if isinstance(state, dict) else len(snapshot_map),
            dirty_questions=self._normalize_dirty_questions(state.get("dirty_questions", [])) if isinstance(state, dict) else [],
            last_refresh_reason=f"module_output_deleted:{question_id}:{module_id}",
        )
        return await self.rebuild_question_record(question_id)

    async def rebuild_question_record(self, question_id: str) -> dict[str, Any]:
        snapshot_map = await self.get_snapshot_map()
        snapshot = snapshot_map.get(question_id) or {}
        record = build_question_record(
            question_id,
            snapshot,
            snapshot_map,
            module_payload_overrides=self._snapshot_module_outputs(snapshot),
            module_run_overrides=self._snapshot_module_runs(snapshot),
        )
        return record

    async def mark_question_dirty(self, question_id: str, *, reason: Optional[str] = None) -> Any:
        try:
            state = await self._state_manager.get_state(_NQ_STATE_KEY)
        except ValueError:
            state = await self._state_manager.bootstrap_state(_NQ_STATE_KEY)
        dirty_questions = (
            state.get("dirty_questions", [])
            if isinstance(state, dict)
            else getattr(state, "dirty_questions", [])
        )
        merged_dirty = self._normalize_dirty_questions([*dirty_questions, question_id])
        last_refresh_reason = f"question_dirty:{question_id}"
        if reason:
            last_refresh_reason = f"{last_refresh_reason}:{reason}"
        updated_state = await self._state_manager.update_state(
            _NQ_STATE_KEY,
            dirty_questions=merged_dirty,
            last_refresh_reason=last_refresh_reason,
        )
        return updated_state

    async def clear_question_dirty(self, question_id: str, *, reason: Optional[str] = None) -> Any:
        try:
            state = await self._state_manager.get_state(_NQ_STATE_KEY)
        except ValueError:
            state = await self._state_manager.bootstrap_state(_NQ_STATE_KEY)
        dirty_questions = (
            state.get("dirty_questions", [])
            if isinstance(state, dict)
            else getattr(state, "dirty_questions", [])
        )
        remaining_dirty = self._normalize_dirty_questions(
            [item for item in dirty_questions if str(item).strip() != question_id]
        )
        last_refresh_reason = f"question_clean:{question_id}"
        if reason:
            last_refresh_reason = f"{last_refresh_reason}:{reason}"
        updated_state = await self._state_manager.update_state(
            _NQ_STATE_KEY,
            dirty_questions=remaining_dirty,
            last_refresh_reason=last_refresh_reason,
        )
        return updated_state

    async def rollback_question(self, question_id: str) -> Any:
        raise RuntimeError(
            "NineQuestionService rollback has been removed because file-backed side storage is no longer allowed"
        )

    async def rollback_question_module(self, question_id: str, module_id: str) -> dict[str, Any]:
        raise RuntimeError(
            "NineQuestionService module rollback has been removed because file-backed side storage is no longer allowed"
        )

    async def rollback_question_module_output(self, question_id: str, module_id: str) -> dict[str, Any]:
        raise RuntimeError(
            "NineQuestionService module-output rollback has been removed because file-backed side storage is no longer allowed"
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute_all(
        self,
        *,
        force: bool = False,
        timeout_seconds: float = 90.0,
        audit: Optional[FlowAudit] = None,
    ) -> Any:
        """Execute all nine questions end-to-end (global bootstrap).

        ``audit`` is forwarded so callers can link child flows (reflection,
        learning) to the same audit_id.  Flow start/end recording is the
        responsibility of the calling layer (web route), not this service.

        Only successful execution paths persist qualified snapshots. Exceptions
        propagate without a final state flush.
        """
        started = time.monotonic()
        config = load_nine_questions_execute_all_config()
        existing_state = await self.get_state()
        has_any_data = self.state_has_any_question_data(existing_state)
        dirty_questions = self._normalize_dirty_questions(
            existing_state.get("dirty_questions", [])
            if isinstance(existing_state, dict)
            else getattr(existing_state, "dirty_questions", [])
        )
        logger.info(
            "[nine-questions] execute_all start force=%s skip_when_q1_q3_unchanged=%s has_any_data=%s dirty_questions=%s timeout=%.1fs",
            force,
            config.skip_refresh_when_q1_q3_unchanged,
            has_any_data,
            dirty_questions,
            timeout_seconds,
        )
        if not force and config.skip_refresh_when_q1_q3_unchanged and has_any_data:
            dirty_q1_q3 = self._dirty_q1_q3_questions(existing_state)
            if not dirty_q1_q3:
                logger.info(
                    "[nine-questions] execute_all skip reason=q1_q3_unchanged elapsed=%.3fs",
                    time.monotonic() - started,
                )
                return await self._state_manager.update_state(
                    _NQ_STATE_KEY,
                    last_refresh_reason="all_nine_questions_skipped_q1_q3_unchanged",
                )

            earliest_dirty = min(dirty_q1_q3, key=EXPECTED_QUESTION_IDS.index)
            start_index = EXPECTED_QUESTION_IDS.index(earliest_dirty)
            run_questions = EXPECTED_QUESTION_IDS[start_index:]
            runner = getattr(self._facade, "run_single_nine_question", None)

            if callable(runner):
                run_question_set = set(run_questions)
                logger.info(
                    "[nine-questions] execute_all incremental earliest_dirty=%s run_questions=%s",
                    earliest_dirty,
                    run_questions,
                )

                def _run_incremental_questions() -> None:
                    for question_id in run_questions:
                        question_started = time.monotonic()
                        logger.info("[nine-questions] execute_all incremental start question=%s", question_id)
                        runner(question_id, max_retries=0)
                        logger.info(
                            "[nine-questions] execute_all incremental end question=%s elapsed=%.3fs",
                            question_id,
                            time.monotonic() - question_started,
                        )

                await asyncio.wait_for(
                    asyncio.to_thread(_run_incremental_questions),
                    timeout=timeout_seconds,
                )
                fresh_kernel_state = self._facade.get_nine_question_state()
                if fresh_kernel_state is not None:
                    await self.persist_kernel_state(fresh_kernel_state)

                refreshed_state = await self.get_state()
                remaining_dirty = [
                    item
                    for item in self._normalize_dirty_questions(
                        refreshed_state.get("dirty_questions", [])
                        if isinstance(refreshed_state, dict)
                        else getattr(refreshed_state, "dirty_questions", [])
                    )
                    if item not in run_question_set
                ]
                updated_state = await self._state_manager.update_state(
                    _NQ_STATE_KEY,
                    dirty_questions=remaining_dirty,
                    last_refresh_reason=f"all_nine_questions_refreshed_q1_q3_changed:{earliest_dirty}",
                )
                logger.info(
                    "[nine-questions] execute_all incremental complete earliest_dirty=%s elapsed=%.3fs",
                    earliest_dirty,
                    time.monotonic() - started,
                )
                return updated_state
            logger.warning(
                "[nine-questions] execute_all incremental runner unavailable; falling back to full bootstrap"
            )
            force = True

        logger.info("[nine-questions] execute_all full_bootstrap start force=%s", force)
        await asyncio.wait_for(
            asyncio.to_thread(self._facade.ensure_nine_questions_bootstrap, force=force),
            timeout=timeout_seconds,
        )
        fresh_kernel_state = self._facade.get_nine_question_state()
        if fresh_kernel_state is not None:
            await self.persist_kernel_state(fresh_kernel_state)
        state = await self.get_state()
        logger.info(
            "[nine-questions] execute_all full_bootstrap complete force=%s elapsed=%.3fs",
            force,
            time.monotonic() - started,
        )
        return state

    async def run_single(
        self,
        question_id: str,
        *,
        timeout_seconds: float = 90.0,
        audit: Optional[FlowAudit] = None,
        runtime_context: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Run a single question in isolation and persist the refreshed baseline."""
        started = time.monotonic()
        logger.info("[nine-questions] run_single stage=mark_dirty_start question_id=%s", question_id)
        await self.mark_question_dirty(question_id, reason="single_run_started")
        logger.info("[nine-questions] run_single stage=mark_dirty_done question_id=%s", question_id)
        snapshot_map = self.get_question_snapshot_map(await self.get_state())
        hydrate_kernel_state = getattr(self._facade, "hydrate_nine_question_state_from_snapshots", None)
        if callable(hydrate_kernel_state):
            logger.info(
                "[nine-questions] run_single stage=hydrate_kernel_state_start question_id=%s snapshot_count=%s",
                question_id,
                len(snapshot_map),
            )
            hydrate_kernel_state(snapshot_map)
            logger.info("[nine-questions] run_single stage=hydrate_kernel_state_done question_id=%s", question_id)
        runner = getattr(self._facade, "run_single_nine_question", None)
        _run = runner if callable(runner) else self._facade.rerun_nine_questions_from

        def _invoke_single() -> Any:
            run_signature = inspect.signature(_run)
            if "max_retries" in run_signature.parameters:
                if "context_overrides" in run_signature.parameters:
                    return _run(
                        question_id,
                        max_retries=0,
                        context_overrides=runtime_context or {},
                    )
                return _run(question_id, max_retries=0)
            if "context_overrides" in run_signature.parameters:
                return _run(question_id, context_overrides=runtime_context or {})
            return _run(question_id)
        logger.info(
            "[nine-questions] run_single stage=kernel_invoke_start question_id=%s timeout_seconds=%s runner=%s",
            question_id,
            timeout_seconds,
            getattr(_run, "__name__", type(_run).__name__),
        )
        run_status = await asyncio.wait_for(
            asyncio.to_thread(_invoke_single),
            timeout=timeout_seconds,
        )
        logger.info("[nine-questions] run_single stage=kernel_invoke_done question_id=%s", question_id)
        fresh_kernel_state = self._facade.get_nine_question_state()
        run_status_value = self._bootstrap_status_value(run_status)
        if run_status_value in {BootstrapStatus.failed.value, BootstrapStatus.partial_failed.value}:
            if fresh_kernel_state is not None:
                logger.info(
                    "[nine-questions] run_single stage=persist_failed_kernel_state_start question_id=%s status=%s",
                    question_id,
                    run_status_value,
                )
                await self.persist_kernel_state(fresh_kernel_state)
                logger.info(
                    "[nine-questions] run_single stage=persist_failed_kernel_state_done question_id=%s status=%s",
                    question_id,
                    run_status_value,
                )
            error_summary = self._question_run_error_summary(fresh_kernel_state, question_id)
            raise RuntimeError(
                f"{question_id} single run ended with status={run_status_value}; "
                f"refusing to report success. {error_summary}".strip()
            )
        if fresh_kernel_state is not None:
            logger.info("[nine-questions] run_single stage=persist_kernel_state_start question_id=%s", question_id)
            await self.persist_kernel_state(fresh_kernel_state)
            logger.info("[nine-questions] run_single stage=persist_kernel_state_done question_id=%s", question_id)
        logger.info("[nine-questions] run_single stage=clear_dirty_start question_id=%s", question_id)
        await self.clear_question_dirty(question_id, reason="single_run_completed")
        logger.info(
            "[nine-questions] run_single stage=completed question_id=%s elapsed=%.3fs",
            question_id,
            time.monotonic() - started,
        )
        return await self.get_state()

    async def rerun_from(
        self,
        question_id: str,
        *,
        timeout_seconds: float = 90.0,
        audit: Optional[FlowAudit] = None,
    ) -> Any:
        """Rerun a specific question and all downstream dependencies.

        Exceptions propagate without a final state flush.
        """
        await self.mark_question_dirty(question_id, reason="downstream_rerun_started")
        await asyncio.wait_for(
            asyncio.to_thread(self._facade.rerun_nine_questions_from, question_id),
            timeout=timeout_seconds,
        )
        fresh_kernel_state = self._facade.get_nine_question_state()
        if fresh_kernel_state is not None:
            await self.persist_kernel_state(fresh_kernel_state)
        await self.clear_question_dirty(question_id, reason="downstream_rerun_completed")
        return await self.get_state()


def sync_q8_tasks_to_task_service(*args: Any, **kwargs: Any) -> Any:
    from zentex.nine_questions.q8_tasks import sync_q8_tasks_to_task_service as _impl

    return _impl(*args, **kwargs)


def sync_q9_tasks_to_task_service(*args: Any, **kwargs: Any) -> Any:
    from zentex.nine_questions.q9_tasks import sync_q9_tasks_to_task_service as _impl

    return _impl(*args, **kwargs)


def derive_posture_baseline(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from plugins.nine_questions.q9_how_should_i_act.modules import derive_posture_baseline as _impl

    return _impl(*args, **kwargs)


def build_q3_capability_inventory(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.capability_propagation import build_q3_capability_inventory as _impl

    return _impl(*args, **kwargs)


def build_q4_action_mapping(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.capability_propagation import build_q4_action_mapping as _impl

    return _impl(*args, **kwargs)


def build_q8_replay_integrity_report(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.q8_replay_integrity import build_q8_replay_integrity_report as _impl

    return _impl(*args, **kwargs)


def verify_turn_to_turn_evolution(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.evolution_verification import verify_turn_to_turn_evolution as _impl

    return _impl(*args, **kwargs)


def build_turn2_learning_evolution_context(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.learning_evolution import build_turn2_learning_evolution_context as _impl

    return _impl(*args, **kwargs)


def build_stock_dataset_manifest(workspace: Any) -> dict[str, Any]:
    import hashlib

    root = Path(workspace).resolve()
    daily_dir = root / "daily"
    tickers = sorted(path.stem for path in daily_dir.glob("*.csv") if path.is_file())
    ticker_set_hash = hashlib.sha256(json.dumps(tickers, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "dataset_family": "stock_multi_ticker",
        "workspace_path": str(root),
        "daily_dir": str(daily_dir),
        "tickers": tickers,
        "ticker_count": len(tickers),
        "ticker_set_hash": ticker_set_hash,
    }


def _memory_record_payload(record: Any) -> dict[str, Any]:
    payload = getattr(record, "payload", None)
    payload = payload if isinstance(payload, dict) else {}
    if "actual_outcome" in payload and isinstance(payload["actual_outcome"], dict):
        return payload["actual_outcome"]
    content = getattr(record, "content", "")
    if isinstance(content, str) and content.strip().startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return payload


def _find_latest_stock_manifest_memory(memory_service: Any, *, query: str, trace_id: str | None = None) -> tuple[Any, dict[str, Any]]:
    candidates: list[Any] = []
    query_fn = getattr(memory_service, "query_managed_records", None)
    if callable(query_fn):
        try:
            candidates.extend(query_fn(limit=100))
        except TypeError:
            candidates.extend(query_fn())
    recall_fn = getattr(memory_service, "recall", None)
    if callable(recall_fn):
        try:
            candidates.extend(recall_fn(query, limit=100))
        except TypeError:
            candidates.extend(recall_fn(query))

    seen: set[str] = set()
    unique_candidates: list[Any] = []
    for candidate in candidates:
        record = getattr(candidate, "record", candidate)
        memory_id = str(getattr(record, "memory_id", "") or "")
        if memory_id and memory_id in seen:
            continue
        if memory_id:
            seen.add(memory_id)
        unique_candidates.append(record)

    for record in reversed(unique_candidates):
        payload = _memory_record_payload(record)
        manifest = payload.get("stock_manifest") if isinstance(payload, dict) else None
        if isinstance(manifest, dict) and manifest.get("ticker_set_hash"):
            if trace_id and str(getattr(record, "trace_id", "") or "") == trace_id:
                continue
            return record, manifest
    raise ValueError("stock manifest memory not found")


def detect_ticker_delta_from_memory(
    *,
    memory_service: Any,
    audit_service: Any,
    current_manifest: dict[str, Any],
    session_id: str,
    trace_id: str,
    turn_id: str,
) -> dict[str, Any]:
    record, previous_manifest = _find_latest_stock_manifest_memory(
        memory_service,
        query="stock ticker baseline memory ticker_set_hash",
        trace_id=trace_id,
    )
    previous_tickers = set(previous_manifest.get("tickers") or [])
    current_tickers = set(current_manifest.get("tickers") or [])
    missing_tickers = sorted(previous_tickers - current_tickers)
    added_tickers = sorted(current_tickers - previous_tickers)
    report = {
        "status": "succeeded",
        "session_id": session_id,
        "trace_id": trace_id,
        "turn_id": turn_id,
        "previous_memory_id": getattr(record, "memory_id", ""),
        "previous_manifest": previous_manifest,
        "current_manifest": current_manifest,
        "missing_tickers": missing_tickers,
        "added_tickers": added_tickers,
        "delta_detected": bool(missing_tickers or added_tickers),
    }
    if audit_service and callable(getattr(audit_service, "record_audit_entry", None)):
        audit_service.record_audit_entry(
            trace_id=trace_id,
            source="zentex.nine_questions.service",
            event_type="memory_delta_detected",
            payload=report,
        )
    return report


def derive_delta_evolution_plan(
    *,
    delta_detection: dict[str, Any],
    audit_service: Any,
    session_id: str,
    trace_id: str,
    turn_id: str,
) -> dict[str, Any]:
    missing_tickers = list(delta_detection.get("missing_tickers") or [])
    q9_profile = {
        "default_action_rhythm_hint": "steady_incremental",
        "specific_posture_scope": {
            "tickers": missing_tickers,
            "action_rhythm_hint": "cautious_slow",
            "confirmation_strategy": "confirm_before_commit",
            "unaffected_tickers": list((delta_detection.get("current_manifest") or {}).get("tickers") or []),
        },
    }
    evolution_report = {
        "status": "agent_logic_evolved",
        "strategy": "strategy_self_optimized",
        "previous_memory_id": delta_detection.get("previous_memory_id"),
        "missing_tickers": missing_tickers,
    }
    plan = {
        "q1_q7_snapshot": {
            "q1": {"memory_delta_detection": delta_detection},
            "q3": {"dataset_family": (delta_detection.get("current_manifest") or {}).get("dataset_family")},
            "q4": {"action_candidates": ["confirm_missing_ticker_delta", "continue_unaffected_tickers"]},
            "q6": {"risk_flags": ["ticker_delta_detected"]},
            "q7": {"alternative_task_paths": ["confirm missing ticker before using evolved strategy"]},
        },
        "q9_profile": q9_profile,
        "evolution_report": evolution_report,
        "next_tasks": [
            {
                "task_id": "memory-delta-learning",
                "title": "Apply memory delta learning",
                "metadata": {
                    "memory_delta_detection": delta_detection,
                    "affected_tickers": missing_tickers,
                    "evolution_report": evolution_report,
                },
                "success_criteria": ["memory_delta_detection recorded", "agent_logic_evolved"],
                "expected_outcome": {"memory_delta_detection": delta_detection, "evolution_report": evolution_report},
            }
        ],
        "proactive_actions": [
            {
                "task_id": "confirm-memory-delta",
                "title": "Confirm ticker delta before broad execution",
                "requires_confirmation": True,
                "metadata": {"missing_tickers": missing_tickers},
            }
        ],
    }
    if audit_service and callable(getattr(audit_service, "record_audit_entry", None)):
        audit_service.record_audit_entry(
            trace_id=trace_id,
            source="zentex.nine_questions.service",
            event_type="memory_delta_plan_derived",
            payload={"session_id": session_id, "turn_id": turn_id, "plan": plan},
        )
    return plan


def derive_turn3_evolved_behavior(
    *,
    memory_service: Any,
    audit_service: Any,
    current_manifest: dict[str, Any],
    session_id: str,
    trace_id: str,
    turn_id: str,
) -> dict[str, Any]:
    record, payload = _find_latest_stock_manifest_memory(
        memory_service,
        query="memory_delta_detection agent_logic_evolved strategy_self_optimized",
        trace_id=trace_id,
    )
    delta_detection = payload.get("memory_delta_detection") if isinstance(payload, dict) else {}
    delta_detection = delta_detection if isinstance(delta_detection, dict) else {}
    missing_tickers = list(delta_detection.get("missing_tickers") or [])
    q9_profile = {
        "default_action_rhythm_hint": "steady_incremental",
        "specific_posture_scope": {
            "tickers": missing_tickers,
            "unaffected_tickers": list(current_manifest.get("tickers") or []),
            "action_rhythm_hint": "cautious_slow",
            "confirmation_strategy": "confirm_before_commit",
        },
    }
    result = {
        "status": "succeeded",
        "session_id": session_id,
        "trace_id": trace_id,
        "turn_id": turn_id,
        "source_evolution_memory_id": getattr(record, "memory_id", ""),
        "current_manifest": current_manifest,
        "q9_profile": q9_profile,
        "q1_q7_snapshot": {
            "q1": {"current_manifest": current_manifest, "source_evolution_memory_id": getattr(record, "memory_id", "")},
            "q3": {"memory_stage": "turn3_evolved_behavior"},
            "q4": {"action_candidates": ["use_evolved_ticker_delta_strategy"]},
            "q7": {"alternative_task_paths": ["keep unaffected tickers steady"]},
        },
        "next_tasks": [
            {
                "task_id": "memory-evolved-turn3",
                "title": "Use evolved memory behavior for unchanged instruction",
                "metadata": {"source_evolution_memory_id": getattr(record, "memory_id", ""), "q9_profile": q9_profile},
                "success_criteria": ["source_evolution_memory_id retained", "specific_posture_scope applied"],
                "expected_outcome": {"source_evolution_memory_id": getattr(record, "memory_id", ""), "q9_profile": q9_profile},
            }
        ],
    }
    if audit_service and callable(getattr(audit_service, "record_audit_entry", None)):
        audit_service.record_audit_entry(
            trace_id=trace_id,
            source="zentex.nine_questions.service",
            event_type="turn3_evolved_behavior_derived",
            payload=result,
        )
    return result

    return _impl(*args, **kwargs)


def build_mixed_executor_orchestration_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.mixed_executor_orchestration import build_mixed_executor_orchestration_plan as _impl

    return _impl(*args, **kwargs)


def scan_resource_gaps(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.resource_recovery import scan_resource_gaps as _impl

    return _impl(*args, **kwargs)


def build_recovery_plan_from_gaps(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.resource_recovery import build_recovery_plan_from_gaps as _impl

    return _impl(*args, **kwargs)


def record_human_resource_fix(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.resource_recovery import record_human_resource_fix as _impl

    return _impl(*args, **kwargs)


async def request_human_resource_confirmation(*args: Any, **kwargs: Any) -> Any:
    from zentex.nine_questions.resource_recovery import request_human_resource_confirmation as _impl

    return await _impl(*args, **kwargs)


async def recover_resource_gap_tasks_after_recheck(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from zentex.nine_questions.resource_recovery import recover_resource_gap_tasks_after_recheck as _impl

    return await _impl(*args, **kwargs)
