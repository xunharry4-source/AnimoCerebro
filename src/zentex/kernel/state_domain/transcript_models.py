"""Transcript model types — plain dataclasses for high-throughput logging."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

UTC = timezone.utc


class TranscriptEntryType(StrEnum):
    turn_start = "turn_start"
    phase_result = "phase_result"
    nine_q_update = "nine_q_update"
    bootstrap_start = "bootstrap_start"
    bootstrap_end = "bootstrap_end"
    turn_end = "turn_end"
    error = "error"
    state_change = "state_change"


@dataclass
class TranscriptEntry:
    """A single record in the transcript log.

    Uses a plain dataclass (not Pydantic) for minimal serialisation overhead
    during high-frequency turn processing.
    """

    entry_type: TranscriptEntryType
    session_id: str
    turn_id: str = ""
    payload: dict = field(default_factory=dict)
    # Set in __post_init__
    entry_id: str = field(default="")
    timestamp: str = field(default="")

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class TurnAuditSummary:
    """Aggregated statistics derived from a completed turn's transcript entries."""

    turn_id: str
    session_id: str
    phase_count: int
    error_count: int
    started_at: str
    ended_at: str
    duration_ms: float
