from __future__ import annotations

"""WorkingMemoryController — bounded, priority-evicting in-memory slot store."""

import threading
from datetime import datetime, timezone

UTC = timezone.utc


class WorkingMemoryController:
    """Manages a fixed number of named slots with priority-based eviction.

    When the store is full and a new key is written, the slot with the
    lowest *priority* value is evicted to make room.  If multiple slots
    share the lowest priority the oldest one (smallest *added_at*) is
    chosen.
    """

    def __init__(self, max_slots: int = 16) -> None:
        self._slots: list[dict] = []
        self._max_slots = max_slots
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, key: str, value: dict, priority: int = 5) -> bool:
        """Insert or update *key* with *value*.

        Returns True if the write completed without eviction, False if an
        existing slot had to be evicted to make room.
        """
        with self._lock:
            # Update in place if the key already exists
            for slot in self._slots:
                if slot["key"] == key:
                    slot["value"] = value
                    slot["priority"] = priority
                    return True

            evicted = False
            if len(self._slots) >= self._max_slots:
                # Evict the lowest-priority (then oldest) slot
                victim = min(
                    self._slots,
                    key=lambda s: (s["priority"], s["added_at"]),
                )
                self._slots.remove(victim)
                evicted = True

            self._slots.append(
                {
                    "key": key,
                    "value": value,
                    "priority": priority,
                    "added_at": datetime.now(UTC).isoformat(),
                }
            )
            return not evicted

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read(self, key: str) -> Optional[dict]:
        """Return the value stored under *key*, or None if absent."""
        with self._lock:
            for slot in self._slots:
                if slot["key"] == key:
                    return slot["value"]
            return None

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def snapshot(self) -> list[dict]:
        """Return a shallow copy of all current slots."""
        with self._lock:
            return list(self._slots)

    def slot_count(self) -> int:
        """Return the number of occupied slots."""
        with self._lock:
            return len(self._slots)

    def budget_remaining(self) -> int:
        """Return the number of slots still available."""
        with self._lock:
            return self._max_slots - len(self._slots)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Empty all slots — typically called between turns."""
        with self._lock:
            self._slots.clear()

    def __repr__(self) -> str:
        return (
            f"WorkingMemoryController("
            f"slots={self.slot_count()}/{self._max_slots})"
        )
