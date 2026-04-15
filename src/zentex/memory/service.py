from __future__ import annotations

"""
Zentex Memory Service Facade.

This module provides a simplified, high-level interface for other Zentex components
to interact with the multi-layered memory engine without needing to manage
internal store paths or complex ingestion logic.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

from zentex.memory.management.enhanced import (
    EnhancedMemoryRecord,
    EnhancedMemoryService,
    ManagedEnhancedMemoryRecord,
    MemoryRecallHit,
)
from zentex.memory.storage.asset_store import AssetDatabaseStore

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Gateway service for the Zentex Memory Engine.
    
    Coordinates semantic, procedural, and episodic layers via a unified API.
    """

    def __init__(self, storage_root: Optional[Union[str, Path]] = None) -> None:
        if storage_root is None:
            # Priority: ZENTEX_MEMORY_ROOT > Project-local app_data > User home
            env_root = os.environ.get("ZENTEX_MEMORY_ROOT")
            if env_root:
                storage_root = Path(env_root)
            else:
                # Try project-local app_data first to avoid home directory permission issues
                project_local = Path(os.getcwd()) / "app_data" / "memory"
                try:
                    project_local.mkdir(parents=True, exist_ok=True)
                    storage_root = project_local
                except Exception:
                    storage_root = Path.home() / ".zentex" / "memory"
        
        self.storage_root = Path(storage_root)
        try:
            self.storage_root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(f"Failed to create storage root at {self.storage_root}: {exc}")
            # Fallback to /tmp as last resort for transient execution
            self.storage_root = Path(f"/tmp/zentex_{uuid4().hex[:8]}/memory")
            self.storage_root.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using ephemeral fallback storage at {self.storage_root}")
        
        # Initialize the target internal service with standard path conventions
        self._internal_service = EnhancedMemoryService(
            semantic_store_path=self.storage_root / "semantic.sqlite3",
            procedural_store_path=self.storage_root / "procedural.sqlite3",
            episodic_store_path=self.storage_root / "episodic.sqlite3",
            management_store_path=self.storage_root / "governance.json",
            audit_store_path=self.storage_root / "audit.sqlite3",
            cold_storage_path=self.storage_root / "cold_archive.sqlite3"
        )
        self._asset_stores: dict[Path, AssetDatabaseStore] = {}
        logger.info(f"MemoryService initialized at {self.storage_root}")

    def get_sharing_bridge(self, aes_key: Optional[bytes] = None) -> Any:
        """Provides a bridge for exporting/importing memory via ZMSP."""
        from zentex.memory.sharing.bridge import ZMSPBridge
        return ZMSPBridge(self._internal_service, aes_key=aes_key)

    def get_sync_engine(self, aes_key: Optional[bytes] = None) -> Any:
        """Provides a sync engine for bidirectional memory replication."""
        from zentex.memory.sharing.sync_engine import SyncEngine
        return SyncEngine(aes_key=aes_key)

    def get_consolidation_engine(self) -> Any:
        """Provides access to the sleep-like memory consolidation engine."""
        from zentex.memory.consolidation.consolidation import ConsolidationEngine
        # Note: In a real scenario, this would need model_provider and other deps
        # which are typically managed by BrainRuntime.
        return getattr(self._internal_service, "consolidation_engine", None)

    def get_asset_store(self, db_path: Optional[Union[str, Path]] = None) -> AssetDatabaseStore:
        """
        Return a shared asset database store under the memory service root.

        This is the controlled facade accessor for task/agent/MCP/plugin asset
        persistence. Callers should use this method instead of importing
        `AssetDatabaseStore` directly.
        """
        target_path = Path(db_path) if db_path is not None else (self.storage_root / "assets.sqlite")
        if not target_path.is_absolute():
            target_path = self.storage_root / target_path
        target_path = target_path.resolve()

        store = self._asset_stores.get(target_path)
        if store is None:
            store = AssetDatabaseStore(target_path)
            self._asset_stores[target_path] = store
        return store

    def remember(
        self,
        *,
        content: str,
        title: str,
        summary: Optional[str] = None,
        layer: str = "semantic",
        source: str = "external_module",
        trace_id: Optional[str] = None,
        tags: Optional[list[str]] = None,
        **metadata: Any
    ) -> EnhancedMemoryRecord:
        """
        Store a new memory record into the specified layer.
        
        Args:
            content: The full content of the memory.
            title: A human-readable title for the memory.
            summary: An optional brief summary.
            layer: The target layer ("semantic", "procedural", "episodic").
            source: The originating source kind.
            trace_id: Optional trace ID for auditability.
            tags: Optional list of labels.
            **metadata: Additional key-value pairs to store in the payload.
            
        Returns:
            The created EnhancedMemoryRecord.
        """
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty.")
        
        return self._internal_service.store_memory(
            title=title,
            summary=summary or title,
            content=content,
            layer=layer,
            source_kind=source,
            trace_id=trace_id,
            tags=tags,
            payload=metadata
        )

    def recall(
        self,
        query: str,
        *,
        limit: int = 10,
        trace_id: Optional[str] = None,
        target_id: Optional[str] = None
    ) -> list[MemoryRecallHit]:
        """
        Perform a hybrid search across memory layers.
        
        Args:
            query: The search query string.
            limit: Maximum number of results to return.
            trace_id: Filter by a specific trace ID.
            target_id: Filter by a specific target ID.
            
        Returns:
            A list of MemoryRecallHit objects sorted by relevance.
        """
        if not query or not query.strip():
            return []
            
        return self._internal_service.recall(
            query=query,
            limit=limit,
            trace_id=trace_id,
            target_id=target_id
        )

    def get_record(self, memory_id: str) -> Optional[ManagedEnhancedMemoryRecord]:
        """Retrieve a specific memory record by its unique ID."""
        return self._internal_service.get_managed_record(memory_id)

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic information about the memory service."""
        return {
            "storage_root": str(self.storage_root),
            "backend_status": [b.model_dump() for b in self._internal_service.get_backend_status()],
            "projection_failures": self._internal_service.list_projection_failures()
        }


# Global singleton instance for easy access
_default_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Return the global default MemoryService instance."""
    global _default_service
    if _default_service is None:
        _default_service = MemoryService()
    return _default_service


def get_service() -> MemoryService:
    """Standard service factory function for launcher assembly.
    
    Alias for get_memory_service() to maintain compatibility
    with the SystemAssembler's expectation of a get_service() function.
    """
    return get_memory_service()
