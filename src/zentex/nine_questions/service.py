from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

from .query import (
    COMPOSED_RECORD_SCHEMA_VERSION,
    _build_flat_upstream_context as _query_build_flat_upstream_context,
    build_question_record,
)
from zentex.common.flow_audit import FlowAudit
from zentex.kernel.cognition_flow.models import BootstrapStatus, NineQuestionState

# Internal SQLite state manager key — nine-questions are global, not per-session.
_NQ_STATE_KEY = "nq-baseline"

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

    @classmethod
    def _append_question_history_version(
        cls,
        *,
        question_id: str,
        current_snapshot: dict[str, Any],
        new_snapshot: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        """Attach a bounded historical version before replacing a canonical snapshot."""
        merged = deepcopy(new_snapshot)
        previous_versions = merged.get("previous_versions")
        history = deepcopy(previous_versions) if isinstance(previous_versions, list) else []

        archived = deepcopy(current_snapshot)
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
            archived.pop(key, None)

        if archived:
            history.append(
                {
                    "question_id": str(question_id),
                    "archived_at": cls._now_iso(),
                    "reason": reason,
                    "snapshot": archived,
                }
            )

        # Keep history bounded to avoid unbounded state growth while preserving
        # enough versions for audit and rollback diagnostics.
        merged["previous_versions"] = history[-20:]
        return merged

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
            return self._serialize_state_payload(state)

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

        return self._serialize_state_payload(state)

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
            responses = state.get("responses")
            if isinstance(responses, dict):
                normalized: dict[str, dict[str, Any]] = {}
                for question_id, response in responses.items():
                    if not isinstance(response, dict):
                        continue
                    normalized[str(question_id)] = {
                        "tool_id": f"nine_questions.{question_id}",
                        "summary": str(response.get("answer") or ""),
                        "confidence": float(response.get("confidence") or 0.0),
                        "result": response,
                        "context_updates": {},
                        "trace_id": f"{question_id}:no-trace",
                    }
                return normalized
            return {}

        snapshots = getattr(state, "question_snapshots", None)
        if isinstance(snapshots, dict):
            return {str(key): value for key, value in snapshots.items() if isinstance(value, dict)}
        responses = getattr(state, "responses", None)
        if isinstance(responses, dict):
            normalized = {}
            for question_id, response in responses.items():
                if not hasattr(response, "answer"):
                    continue
                normalized[str(question_id)] = {
                    "tool_id": f"nine_questions.{question_id}",
                    "summary": str(getattr(response, "answer", "") or ""),
                    "confidence": float(getattr(response, "confidence", 0.0) or 0.0),
                    "result": {
                        "question_id": question_id,
                        "answer": str(getattr(response, "answer", "") or ""),
                        "confidence": float(getattr(response, "confidence", 0.0) or 0.0),
                        "error": str(getattr(response, "error", "") or ""),
                    },
                    "context_updates": {},
                    "trace_id": f"{question_id}:no-trace",
                }
            return normalized
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
        """Mirror kernel nine-question results into the persisted state store.

        Uses a MERGE strategy rather than a full overwrite:
        - For each question, if the incoming snapshot is worse (empty / failed)
          than what is already persisted, the existing record is kept.
        - Only execution-diagnosis metadata from the new run is merged in so
          the UI can reflect that a re-run was attempted.

        This preserves the nine-questions partial-success contract: a failed
        full-update must never delete previously successful question answers.
        """
        snapshot_map = self.get_question_snapshot_map(state)
        if not snapshot_map:
            return

        # Ensure the SQLite row exists; read existing snapshot data for merge.
        try:
            existing_state = await self._state_manager.get_state(_NQ_STATE_KEY)
            existing_snapshot_map = self.get_question_snapshot_map(existing_state)
        except ValueError:
            existing_snapshot_map = {}
            await self._state_manager.bootstrap_state(_NQ_STATE_KEY)

        # Merge: accept new data only when it is genuinely better.
        merged_snapshot_map: dict[str, Any] = dict(existing_snapshot_map)
        for question_id, new_snapshot in snapshot_map.items():
            existing_snapshot = existing_snapshot_map.get(question_id)
            decision = self._should_accept_new_snapshot(existing_snapshot, new_snapshot)
            if decision["accept_snapshot"]:
                if isinstance(existing_snapshot, dict):
                    merged_snapshot_map[question_id] = self._append_question_history_version(
                        question_id=question_id,
                        current_snapshot=existing_snapshot,
                        new_snapshot=new_snapshot,
                        reason=str(decision.get("reason") or "new_snapshot_accepted"),
                    )
                else:
                    merged_snapshot_map[question_id] = new_snapshot
            else:
                # Keep existing answer; only propagate diagnostic metadata.
                rejected_merge = self._merge_diagnostic_only(
                    existing_snapshot,  # type: ignore[arg-type]
                    new_snapshot,
                )
                if isinstance(existing_snapshot, dict):
                    rejected_merge = self._append_question_history_version(
                        question_id=question_id,
                        current_snapshot=existing_snapshot,
                        new_snapshot=rejected_merge,
                        reason=str(decision.get("reason") or "new_snapshot_rejected"),
                    )
                merged_snapshot_map[question_id] = rejected_merge
        merged_snapshot_map = self._normalize_snapshot_map_metadata(
            merged_snapshot_map,
            touch_updated_at=True,
        )

        if isinstance(state, dict):
            snapshot_version = int(state.get("snapshot_version", len(merged_snapshot_map)))
            last_refresh_reason = state.get("last_refresh_reason")
            dirty_questions = self._normalize_dirty_questions(state.get("dirty_questions"))
        else:
            snapshot_version = int(getattr(state, "snapshot_version", len(merged_snapshot_map)))
            last_refresh_reason = getattr(state, "last_refresh_reason", None)
            dirty_questions = self._normalize_dirty_questions(getattr(state, "dirty_questions", []))

        await self._state_manager.update_state(
            _NQ_STATE_KEY,
            question_snapshots=merged_snapshot_map,
            snapshot_version=snapshot_version,
            last_refresh_reason=last_refresh_reason,
            dirty_questions=dirty_questions,
        )

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    async def get_state(self) -> Any:
        """Return the authoritative nine-question baseline state."""
        try:
            persisted_state = await self._state_manager.get_state(_NQ_STATE_KEY)
        except ValueError:
            persisted_state = None

        # 1. Prefer fresh in-memory kernel state when it is newer or differs from persisted state.
        live_state = self._facade.get_nine_question_state()
        if self.live_state_should_replace_persisted(persisted_state, live_state):
            await self.persist_kernel_state(live_state)
            return live_state

        # 2. Fall back to ready persisted state.
        if (
            persisted_state is not None
            and self.state_has_complete_question_data(persisted_state)
            and not self.state_requires_refresh(persisted_state)
        ):
            return persisted_state

        # 3. If persisted exists but is incomplete/stale, return it (let UI handle refresh)
        if persisted_state is not None:
            return persisted_state

        # 4. No state at all — bootstrap a blank 'not_started' record in memory
        try:
            return await self._state_manager.get_state(_NQ_STATE_KEY)
        except ValueError:
            return await self._state_manager.bootstrap_state(_NQ_STATE_KEY)

    async def get_snapshot_map(self) -> dict[str, dict[str, Any]]:
        return self.get_question_snapshot_map(await self.get_state())

    async def get_question_snapshot(self, question_id: str) -> dict[str, Any]:
        return (await self.get_snapshot_map()).get(question_id)

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
        await self.get_state()
        snapshot_map = await self.get_snapshot_map()
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

    async def get_question_modules(self, question_id: str) -> dict[str, Any]:
        record = await self.get_question_record(question_id)
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
        merged_snapshot = self._append_question_history_version(
            question_id=question_id,
            current_snapshot=current_snapshot,
            new_snapshot=merged_snapshot,
            reason=str(decision.get("reason") or refresh_reason or "question_snapshot_patch"),
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

    async def persist_question_module_run(
        self,
        question_id: str,
        module_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
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
        force: bool = True,
        timeout_seconds: float = 90.0,
        audit: Optional[FlowAudit] = None,
    ) -> Any:
        """Execute all nine questions end-to-end (global bootstrap).

        ``audit`` is forwarded so callers can link child flows (reflection,
        learning) to the same audit_id.  Flow start/end recording is the
        responsibility of the calling layer (web route), not this service.

        persist_kernel_state() is called unconditionally in a finally block so
        that partial progress is never lost on timeout or exception (P1-Fix-A).
        The merge-write strategy in persist_kernel_state() ensures a failed run
        cannot overwrite previously successful answers (P3-Fix-A).
        """
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._facade.ensure_nine_questions_bootstrap, force=force),
                timeout=timeout_seconds,
            )
        except Exception:
            logger.warning(
                "execute_all: bootstrap ended with exception; flushing partial kernel state",
                exc_info=True,
            )
            raise
        finally:
            fresh_kernel_state = self._facade.get_nine_question_state()
            if fresh_kernel_state is not None:
                await self.persist_kernel_state(fresh_kernel_state)
        return await self.get_state()

    async def run_single(
        self,
        question_id: str,
        *,
        timeout_seconds: float = 90.0,
        audit: Optional[FlowAudit] = None,
    ) -> Any:
        """Run a single question in isolation and persist only the refreshed baseline.

        persist_kernel_state() is called in a finally block so partial module
        progress is never lost even when execution times out or raises (P1-Fix-A).
        """
        await self.mark_question_dirty(question_id, reason="single_run_started")
        runner = getattr(self._facade, "run_single_nine_question", None)
        _run = runner if callable(runner) else self._facade.rerun_nine_questions_from

        def _invoke_single() -> Any:
            run_signature = inspect.signature(_run)
            if "max_retries" in run_signature.parameters:
                return _run(question_id, max_retries=0)
            return _run(question_id)
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_invoke_single),
                timeout=timeout_seconds,
            )
        except Exception:
            logger.warning(
                "run_single %s: execution ended with exception; flushing partial kernel state",
                question_id,
                exc_info=True,
            )
            raise
        finally:
            fresh_kernel_state = self._facade.get_nine_question_state()
            if fresh_kernel_state is not None:
                await self.persist_kernel_state(fresh_kernel_state)
        await self.clear_question_dirty(question_id, reason="single_run_completed")
        return await self.get_state()

    async def rerun_from(
        self,
        question_id: str,
        *,
        timeout_seconds: float = 90.0,
        audit: Optional[FlowAudit] = None,
    ) -> Any:
        """Rerun a specific question and all downstream dependencies.

        persist_kernel_state() is called in a finally block (P1-Fix-A).
        """
        await self.mark_question_dirty(question_id, reason="downstream_rerun_started")
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._facade.rerun_nine_questions_from, question_id),
                timeout=timeout_seconds,
            )
        except Exception:
            logger.warning(
                "rerun_from %s: execution ended with exception; flushing partial kernel state",
                question_id,
                exc_info=True,
            )
            raise
        finally:
            fresh_kernel_state = self._facade.get_nine_question_state()
            if fresh_kernel_state is not None:
                await self.persist_kernel_state(fresh_kernel_state)
        await self.clear_question_dirty(question_id, reason="downstream_rerun_completed")
        return await self.get_state()
