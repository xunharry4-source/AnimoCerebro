"""
Context Snapshot Store / 上下文快照存储

Manages time-series context snapshots for historical analysis and state recovery.
Provides storage, retrieval, and querying capabilities for context snapshots.

管理时间序列上下文快照，用于历史分析和状态恢复。
提供上下文快照的存储、检索和查询功能。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from zentex.environment.models import ContextSnapshot, PhysicalHostState


class ContextSnapshotStore:
    """
    Stores and manages context snapshots over time.
    
    上下文快照存储，随时间存储和管理上下文快照。
    
    Provides append-only storage for context snapshots with support for
    time-series queries, filtering, and retrieval. Snapshots can be
    persisted to disk for durability across restarts.
    
    提供上下文快照的追加式存储，支持时间序列查询、过滤和检索。
    快照可以持久化到磁盘以在重启后保持耐用性。
    """
    
    def __init__(
        self,
        *,
        storage_path: str | None = None,
        max_in_memory_snapshots: int = 1000,
    ) -> None:
        """
        Initialize the ContextSnapshotStore.
        
        Args:
            storage_path: Path to store snapshots on disk (optional)
            max_in_memory_snapshots: Maximum snapshots to keep in memory
        """
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_in_memory_snapshots = max_in_memory_snapshots
        
        self._lock = Lock()
        self._snapshots: list[ContextSnapshot] = []
        self._snapshot_index: dict[str, int] = {}  # snapshot_id -> index
        
        # Load existing snapshots if storage path provided
        if self.storage_path:
            self._load_from_disk()
    
    def add_snapshot(self, snapshot: ContextSnapshot) -> None:
        """
        Add a new context snapshot to the store.
        
        向存储中添加新的上下文快照。
        
        Args:
            snapshot: The context snapshot to add
        """
        with self._lock:
            # Add to in-memory store
            self._snapshots.append(snapshot)
            self._snapshot_index[snapshot.snapshot_id] = len(self._snapshots) - 1
            
            # Enforce maximum size (remove oldest if exceeded)
            if len(self._snapshots) > self.max_in_memory_snapshots:
                removed = self._snapshots.pop(0)
                del self._snapshot_index[removed.snapshot_id]
            
            # Persist to disk if configured
            if self.storage_path:
                self._append_to_disk(snapshot)
    
    def create_snapshot(
        self,
        host_state: PhysicalHostState | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        active_goals: list[str] | None = None,
        working_memory_summary: str | None = None,
        current_role: str | None = None,
        identity_anchor_ref: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextSnapshot:
        """
        Create and add a new context snapshot.
        
        创建并添加新的上下文快照。
        
        Convenience method that creates a snapshot from individual parameters.
        
        Args:
            host_state: Physical host state at snapshot time
            session_id: Associated session ID
            turn_id: Associated think loop turn ID
            active_goals: List of active goal IDs
            working_memory_summary: Summary of working memory
            current_role: Current agent role
            identity_anchor_ref: Reference to identity kernel
            tags: Tags for categorization
            metadata: Additional metadata
            
        Returns:
            The created ContextSnapshot
        """
        snapshot = ContextSnapshot(
            snapshot_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            session_id=session_id,
            turn_id=turn_id,
            host_state=host_state,
            active_goals=active_goals or [],
            working_memory_summary=working_memory_summary,
            current_role=current_role,
            identity_anchor_ref=identity_anchor_ref,
            tags=tags or [],
            metadata=metadata or {},
        )
        
        self.add_snapshot(snapshot)
        return snapshot
    
    def get_snapshot(self, snapshot_id: str) -> ContextSnapshot | None:
        """
        Retrieve a specific snapshot by ID.
        
        按 ID 检索特定快照。
        
        Args:
            snapshot_id: ID of the snapshot to retrieve
            
        Returns:
            The snapshot if found, None otherwise
        """
        with self._lock:
            index = self._snapshot_index.get(snapshot_id)
            if index is not None and index < len(self._snapshots):
                return self._snapshots[index]
            return None
    
    def get_recent_snapshots(
        self,
        count: int = 10,
        before_timestamp: datetime | None = None,
    ) -> list[ContextSnapshot]:
        """
        Get the most recent snapshots.
        
        获取最近的快照。
        
        Args:
            count: Number of snapshots to retrieve
            before_timestamp: Only return snapshots before this time
            
        Returns:
            List of recent snapshots, ordered newest first
        """
        with self._lock:
            # Filter by timestamp if specified
            filtered = self._snapshots
            if before_timestamp:
                filtered = [
                    s for s in filtered if s.timestamp <= before_timestamp
                ]
            
            # Return most recent
            return list(reversed(filtered[-count:]))
    
    def query_snapshots(
        self,
        session_id: str | None = None,
        turn_id: str | None = None,
        tag: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ContextSnapshot]:
        """
        Query snapshots with various filters.
        
        使用各种过滤器查询快照。
        
        Args:
            session_id: Filter by session ID
            turn_id: Filter by turn ID
            tag: Filter by tag (must be present in snapshot's tags)
            start_time: Only return snapshots after this time
            end_time: Only return snapshots before this time
            
        Returns:
            List of matching snapshots
        """
        with self._lock:
            results = self._snapshots
            
            # Apply filters
            if session_id:
                results = [s for s in results if s.session_id == session_id]
            
            if turn_id:
                results = [s for s in results if s.turn_id == turn_id]
            
            if tag:
                results = [s for s in results if tag in s.tags]
            
            if start_time:
                results = [s for s in results if s.timestamp >= start_time]
            
            if end_time:
                results = [s for s in results if s.timestamp <= end_time]
            
            return results
    
    def get_snapshot_count(self) -> int:
        """Get the total number of snapshots in the store."""
        with self._lock:
            return len(self._snapshots)
    
    def clear(self) -> None:
        """Clear all snapshots from the store."""
        with self._lock:
            self._snapshots.clear()
            self._snapshot_index.clear()
    
    def _append_to_disk(self, snapshot: ContextSnapshot) -> None:
        """Append a single snapshot to disk storage."""
        if not self.storage_path:
            return
        
        try:
            # Ensure directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Append as JSON line
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(snapshot.model_dump_json() + "\n")
        except Exception as e:
            # Log error but don't fail the operation
            print(f"Warning: Failed to persist snapshot to disk: {e}")
    
    def _load_from_disk(self) -> None:
        """Load existing snapshots from disk storage."""
        if not self.storage_path or not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        snapshot = ContextSnapshot(**data)
                        self._snapshots.append(snapshot)
                        self._snapshot_index[snapshot.snapshot_id] = len(self._snapshots) - 1
                    except Exception as e:
                        print(f"Warning: Failed to load snapshot from disk: {e}")
                        
                        # Trim to max size
                        if len(self._snapshots) > self.max_in_memory_snapshots:
                            excess = len(self._snapshots) - self.max_in_memory_snapshots
                            self._snapshots = self._snapshots[excess:]
                            # Rebuild index
                            self._snapshot_index = {
                                s.snapshot_id: i
                                for i, s in enumerate(self._snapshots)
                            }
        except Exception as e:
            print(f"Warning: Failed to load snapshots from disk: {e}")
