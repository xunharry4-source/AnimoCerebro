from __future__ import annotations

"""
BrainTranscriptStore / 记忆事件流

EN:
BrainTranscriptStore is the low-level JSONL or SQLite physical storage and
deserialization layer. It records the brain log as an append-only runtime
event stream.

ZH:
BrainTranscriptStore（记忆事件流）：纯底层的 JSONL/SQLite 物理存储与反序列化，
记录大脑日志。
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from threading import Condition, Lock
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from uuid import uuid4
from collections.abc import Callable


JSONScalar = Union[str, int, float, bool, None]
JSONValue = Union[JSONScalar, List["JSONValue"], Dict[str, "JSONValue"]]


class BrainTranscriptEntryType(str, Enum):
    SESSION_STARTED = "session_started"
    TURN_STARTED = "turn_started"
    CONTEXT_SNAPSHOT_WRITTEN = "context_snapshot_written"
    WORKING_MEMORY_UPDATED = "working_memory_updated"
    TEMPORAL_AGENDA_UPDATED = "temporal_agenda_updated"
    LIVING_SELF_MODEL_UPDATED = "living_self_model_updated"
    CONFLICT_SNAPSHOT_WRITTEN = "conflict_snapshot_written"
    COUNTERFACTUAL_COMPLETED = "counterfactual_completed"
    INTERACTION_MIND_UPDATED = "interaction_mind_updated"
    METACOGNITION_DECIDED = "metacognition_decided"
    COGNITIVE_TOOL_INVOKED = "cognitive_tool_invoked"
    COGNITIVE_TOOL_COMPLETED = "cognitive_tool_completed"
    MODEL_PROVIDER_INVOKED = "model_provider_invoked"
    MODEL_PROVIDER_COMPLETED = "model_provider_completed"
    MODEL_PROVIDER_FAILED = "model_provider_failed"
    DECISION_SYNTHESIZED = "decision_synthesized"
    REFLECTION_PERSISTED = "reflection_persisted"
    CONSOLIDATION_COMPLETED = "consolidation_completed"
    CONSOLIDATION_FAILED = "consolidation_failed"
    HUMAN_INTERVENTION_APPLIED = "human_intervention_applied"
    NINE_QUESTION_STATE_UPDATED = "nine_question_state_updated"
    PLUGIN_AUDIT_EVENT = "plugin_audit_event"
    LEARNING_ENGINE_EVENT = "learning_engine_event"
    TURN_FINISHED = "turn_finished"


@dataclass(frozen=True)
class BrainTranscriptEntry:
    entry_id: str
    session_id: str
    turn_id: str
    entry_type: BrainTranscriptEntryType
    timestamp: datetime
    payload: JSONValue
    source: str
    trace_id: str

    def to_record(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "entry_type": self.entry_type.value,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "payload": self.payload,
            "source": self.source,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "BrainTranscriptEntry":
        return cls(
            entry_id=str(record["entry_id"]),
            session_id=str(record["session_id"]),
            turn_id=str(record["turn_id"]),
            entry_type=BrainTranscriptEntryType(record["entry_type"]),
            timestamp=datetime.fromisoformat(str(record["timestamp"])),
            payload=record["payload"],
            source=str(record["source"]),
            trace_id=str(record["trace_id"]),
        )


class BrainTranscriptStore:
    """
    Append-only runtime event stream for replay and session restore.

    This store records what happened during execution. It does not replace:
    - ReflectionStore: durable reflection artifacts
    - RuntimeMemoryStore: durable memory objects
    """

    def __init__(
        self,
        file_path: str | Path,
        *,
        entry_listeners: Iterable[Callable[[BrainTranscriptEntry], None]] | None = None,
    ) -> None:
        self._file_path = Path(file_path)
        self._write_lock = Lock()
        self._revision_condition = Condition()
        self._revision = 0
        self._entries_cache: list[BrainTranscriptEntry] | None = None
        self._cache_stat_sig: tuple[int, int] | None = None
        self._index_stat_sig: tuple[int, int] | None = None
        self._turn_index: dict[str, list[BrainTranscriptEntry]] | None = None
        self._trace_index: dict[str, list[BrainTranscriptEntry]] | None = None
        self._entry_listeners: list[Callable[[BrainTranscriptEntry], None]] = list(entry_listeners or [])
        self._listener_failures: list[str] = []
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def file_path(self) -> Path:
        return self._file_path

    def append_entries(self, entries: Iterable[BrainTranscriptEntry]) -> List[BrainTranscriptEntry]:
        """Bulk append entries to the transcript with a single lock acquisition."""
        entries_list = list(entries)
        if not entries_list:
            return []
        
        records = [json.dumps(e.to_record(), ensure_ascii=False) for e in entries_list]
        with self._write_lock:
            with self._file_path.open("a", encoding="utf-8") as handle:
                for line in records:
                    handle.write(line)
                    handle.write("\n")
            
            if self._entries_cache is not None:
                self._entries_cache.extend(entries_list)
                stat = self._file_path.stat()
                self._cache_stat_sig = (stat.st_size, stat.st_mtime_ns)
                if (
                    self._index_stat_sig == self._cache_stat_sig
                    and self._turn_index is not None
                    and self._trace_index is not None
                ):
                    for entry in entries_list:
                        self._turn_index.setdefault(entry.turn_id, []).append(entry)
                        self._trace_index.setdefault(entry.trace_id, []).append(entry)

        for entry in entries_list:
            for listener in list(self._entry_listeners):
                try:
                    listener(entry)
                except Exception as exc:  # pragma: no cover
                    message = str(exc).strip() or exc.__class__.__name__
                    with self._write_lock:
                        self._listener_failures.append(message)
        
        with self._revision_condition:
            self._revision += 1
            self._revision_condition.notify_all()
        return entries_list

    def append_entry(self, entry: BrainTranscriptEntry) -> BrainTranscriptEntry:
        line = json.dumps(entry.to_record(), ensure_ascii=False)
        with self._write_lock:
            with self._file_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
            if self._entries_cache is not None:
                self._entries_cache.append(entry)
                stat = self._file_path.stat()
                self._cache_stat_sig = (stat.st_size, stat.st_mtime_ns)
                if (
                    self._index_stat_sig == self._cache_stat_sig
                    and self._turn_index is not None
                    and self._trace_index is not None
                ):
                    self._turn_index.setdefault(entry.turn_id, []).append(entry)
                    self._trace_index.setdefault(entry.trace_id, []).append(entry)
        for listener in list(self._entry_listeners):
            try:
                listener(entry)
            except Exception as exc:  # pragma: no cover - defensive listener isolation
                message = str(exc).strip() or exc.__class__.__name__
                with self._write_lock:
                    self._listener_failures.append(message)
        with self._revision_condition:
            self._revision += 1
            self._revision_condition.notify_all()
        return entry

    def register_entry_listener(
        self,
        listener: Callable[[BrainTranscriptEntry], None],
    ) -> None:
        """Register a best-effort listener without weakening transcript durability."""
        with self._write_lock:
            self._entry_listeners.append(listener)

    def list_listener_failures(self) -> list[str]:
        """Return non-fatal listener projection failures for inspection."""
        with self._write_lock:
            return list(self._listener_failures)

    def write_entry(
        self,
        *,
        session_id: str,
        turn_id: str,
        entry_type: BrainTranscriptEntryType,
        payload: JSONValue,
        source: str,
        trace_id: str,
        entry_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> BrainTranscriptEntry:
        entry = BrainTranscriptEntry(
            entry_id=entry_id or str(uuid4()),
            session_id=session_id,
            turn_id=turn_id,
            entry_type=entry_type,
            timestamp=timestamp or datetime.now(timezone.utc),
            payload=payload,
            source=source,
            trace_id=trace_id,
        )
        return self.append_entry(entry)

    def append(self, event: Dict[str, Any]) -> None:
        """
        Compatibility audit sink for plugin registries.

        Some registries require an `append(event)` interface so tests can assert
        against exact audit payloads. In production we still persist those audit
        payloads into the transcript stream as structured entries.
        """
        plugin_id = str(event.get("plugin_id") or "unknown")
        self.write_entry(
            session_id="plugin-audit",
            turn_id=f"plugin-audit:{plugin_id}",
            entry_type=BrainTranscriptEntryType.PLUGIN_AUDIT_EVENT,
            payload=event,
            source="runtime.transcript.plugin_audit",
            trace_id=f"plugin-audit:{plugin_id}",
        )

    def read_by_session_id(self, session_id: str) -> List[BrainTranscriptEntry]:
        return self.read_entries(session_id=session_id)

    def read_entries(self, *, session_id: Optional[str] = None, turn_id: Optional[str] = None) -> List[BrainTranscriptEntry]:
        """
        Multi-factor read for the clinical record.
        """
        entries = self.get_entries_snapshot()
        if session_id:
            entries = [e for e in entries if e.session_id == session_id]
        if turn_id:
            entries = [e for e in entries if e.turn_id == turn_id]
        return entries

    def search_entries(self, *, trace_id: Optional[str] = None, source: Optional[str] = None) -> List[BrainTranscriptEntry]:
        """
        Global search across the entire physical transcript.
        """
        entries = self.get_entries_snapshot()
        if trace_id:
            entries = [e for e in entries if e.trace_id == trace_id]
        if source:
            entries = [e for e in entries if e.source == source]
        return entries

    def read_by_turn_id(self, turn_id: str) -> List[BrainTranscriptEntry]:
        self._ensure_indexes()
        if self._turn_index is None:
            return []
        return list(self._turn_index.get(turn_id, []))

    def read_by_trace_id(self, trace_id: str) -> List[BrainTranscriptEntry]:
        self._ensure_indexes()
        if self._trace_index is None:
            return []
        return list(self._trace_index.get(trace_id, []))

    def read_by_session_and_turn_id(self, session_id: str, turn_id: str) -> List[BrainTranscriptEntry]:
        return [
            entry
            for entry in self.read_by_turn_id(turn_id)
            if entry.session_id == session_id
        ]

    def iter_entries(self) -> Iterable[BrainTranscriptEntry]:
        return iter(self.get_entries_snapshot())

    def get_entries_snapshot(self) -> List[BrainTranscriptEntry]:
        with self._write_lock:
            if not self._file_path.exists():
                self._entries_cache = []
                self._cache_stat_sig = (0, 0)
                self._index_stat_sig = (0, 0)
                self._turn_index = {}
                self._trace_index = {}
                return self._entries_cache
            stat = self._file_path.stat()
            stat_sig = (stat.st_size, stat.st_mtime_ns)
            if self._entries_cache is not None and self._cache_stat_sig == stat_sig:
                return self._entries_cache
            entries = list(self._iter_entries_from_disk())
            self._entries_cache = entries
            self._cache_stat_sig = stat_sig
            self._index_stat_sig = None
            self._turn_index = None
            self._trace_index = None
            return entries

    def get_revision(self) -> int:
        with self._revision_condition:
            return self._revision

    def wait_for_revision_after(self, revision: int, timeout: Optional[float] = None) -> bool:
        with self._revision_condition:
            if self._revision > revision:
                return True
            return self._revision_condition.wait_for(
                lambda: self._revision > revision,
                timeout=timeout,
            )

    def _iter_entries_from_disk(self) -> Iterable[BrainTranscriptEntry]:
        with self._file_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    yield BrainTranscriptEntry.from_record(record)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Invalid transcript entry at line {line_number} "
                        f"in {self._file_path}"
                    ) from exc

    def _ensure_indexes(self) -> None:
        entries = self.get_entries_snapshot()
        with self._write_lock:
            stat_sig = self._cache_stat_sig or (0, 0)
            if self._index_stat_sig == stat_sig and self._turn_index is not None and self._trace_index is not None:
                return
            turn_index: Dict[str, List[BrainTranscriptEntry]] = {}
            trace_index: Dict[str, List[BrainTranscriptEntry]] = {}
            for entry in entries:
                turn_index.setdefault(entry.turn_id, []).append(entry)
                trace_index.setdefault(entry.trace_id, []).append(entry)
            self._turn_index = turn_index
            self._trace_index = trace_index
            self._index_stat_sig = stat_sig
