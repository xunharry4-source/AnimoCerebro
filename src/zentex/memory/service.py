from __future__ import annotations

"""
Zentex Memory Service Facade.

This module provides a simplified, high-level interface for other Zentex components
to interact with the multi-layered memory engine without needing to manage
internal store paths or complex ingestion logic.
"""

import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional, Union

from zentex.memory.management.enhanced import (
    EnhancedMemoryRecord,
    EnhancedMemoryService,
    EpisodeGraphMemoryAdapter,
    ManagedEnhancedMemoryRecord,
    MemoryRecallHit,
)
from zentex.memory.storage.kuzu_backend import KuzuGraphMemoryClient
from zentex.memory.storage.asset_store import AssetDatabaseStore
from zentex.common.storage_paths import get_storage_paths

logger = logging.getLogger(__name__)


def build_default_episode_graph_adapter() -> EpisodeGraphMemoryAdapter:
    db_path = get_storage_paths().runtime_data_dir / "memory" / "kuzu_db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return EpisodeGraphMemoryAdapter(graph_client=KuzuGraphMemoryClient(db_path=str(db_path)))


class MemoryService:
    """
    Gateway service for the Zentex Memory Engine.
    
    Coordinates semantic, procedural, and episodic layers via a unified API.
    """

    def __init__(self, storage_root: Optional[Union[str, Path]] = None) -> None:
        if storage_root is None:
            env_root = os.environ.get("ZENTEX_MEMORY_ROOT")
            if env_root:
                storage_root = Path(env_root)
            else:
                storage_root = get_storage_paths().app_data_dir / "memory"
        
        self.storage_root = Path(storage_root)
        try:
            self.storage_root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(f"Failed to create storage root at {self.storage_root}: {exc}")
            raise RuntimeError(f"MemoryService storage root unavailable: {self.storage_root}") from exc
        
        # Initialize the target internal service with standard path conventions
        self._internal_service = EnhancedMemoryService(
            semantic_store_path=self.storage_root / "semantic.sqlite3",
            procedural_store_path=self.storage_root / "procedural.sqlite3",
            episodic_store_path=self.storage_root / "episodic.sqlite3",
            management_store_path=self.storage_root / "governance_state.sqlite3",
            audit_store_path=self.storage_root / "audit.sqlite3",
            cold_storage_path=self.storage_root / "cold_archive.sqlite3"
        )
        self._asset_stores: dict[Path, AssetDatabaseStore] = {}
        self._consolidation_lock = threading.Lock()
        self._consolidation_bridge: Any = None
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
        return self._ensure_consolidation_stack()[0]

    def trigger_manual_consolidation(self, *, operator: str = "memory_service_manual") -> Any:
        """
        Queue a consolidation cycle through the public memory facade.

        The cycle runs in the background and writes its governance updates back
        into enhanced memory through the consolidation bridge.
        """
        import uuid

        engine, bridge = self._ensure_consolidation_stack()
        handle, future = engine.submit_cycle(
            trigger_stage="sleep_phase",
            input_memory_refs=[],
            noise_rules=[],
            context={"operator": operator, "trigger": "manual"},
            idempotency_key=str(uuid.uuid4()),
            snapshot_version=engine.snapshot_version,
        )
        self._attach_consolidation_bridge(future=future, bridge=bridge)
        return handle

    def trigger_automatic_consolidation_check(self) -> Any:
        """
        Expose the engine's automatic consolidation decision path via service.py.

        This lets callers invoke the same budget/idle checks manually from the
        service boundary without importing consolidation internals directly.
        """
        engine, _bridge = self._ensure_consolidation_stack()
        return engine.check_and_trigger_automatic_consolidation()

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
        target_id: Optional[str] = None,
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
            target_id: Optional target ID for exact linkage/filtering.
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
            target_id=target_id,
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

    async def initialize_background(self) -> None:
        await self._internal_service.initialize_background()

    def bind_episodic_adapter(self, adapter: Any) -> None:
        self._internal_service._episodic_sink = adapter
        self._internal_service._episodic_recall_client = adapter

    def list_semantic_records(self) -> list[EnhancedMemoryRecord]:
        return self._internal_service.list_semantic_records()

    def list_procedural_records(self) -> list[EnhancedMemoryRecord]:
        return self._internal_service.list_procedural_records()

    def list_episodic_records(self) -> list[EnhancedMemoryRecord]:
        return self._internal_service.list_episodic_records()

    def list_managed_records(self, *args: Any, **kwargs: Any) -> list[ManagedEnhancedMemoryRecord]:
        return self._internal_service.list_managed_records(*args, **kwargs)

    def query_managed_records(self, *args: Any, **kwargs: Any) -> list[ManagedEnhancedMemoryRecord]:
        return self._internal_service.query_managed_records(*args, **kwargs)

    def list_projection_failures(self) -> list[str]:
        return self._internal_service.list_projection_failures()

    def list_initialization_failures(self) -> list[str]:
        return self._internal_service.list_initialization_failures()

    def list_governance_failures(self) -> list[str]:
        return self._internal_service.list_governance_failures()

    def get_health_snapshot(self) -> dict[str, Any]:
        return self._internal_service.get_health_snapshot()

    def get_backend_status(self) -> list[Any]:
        return self._internal_service.get_backend_status()

    def list_audit_events(self, *args: Any, **kwargs: Any) -> list[Any]:
        return self._internal_service.list_audit_events(*args, **kwargs)

    def get_record_header(self, memory_id: str) -> Any:
        return self._internal_service.get_record_header(memory_id)

    def get_record_manifest(self, memory_id: str) -> Any:
        return self._internal_service.get_record_manifest(memory_id)

    def verify_record(self, memory_id: str) -> Any:
        return self._internal_service.verify_record(memory_id)

    def repair_record(self, memory_id: str) -> Any:
        return self._internal_service.repair_record(memory_id)

    def repair_all(self) -> list[Any]:
        return self._internal_service.repair_all()

    def update_management_state(self, memory_id: str, **kwargs: Any) -> ManagedEnhancedMemoryRecord:
        return self._internal_service.update_management_state(memory_id, **kwargs)

    def archive_memory(
        self,
        memory_id: str,
        *,
        reason: str = "Archived by operator.",
        operator: str = "operator",
    ) -> ManagedEnhancedMemoryRecord:
        return self._internal_service.archive_memory(
            memory_id,
            reason=reason,
            operator=operator,
        )

    def backfill_transcript_entries(self, entries: list[Any]) -> None:
        self._internal_service.backfill_transcript_entries(entries)

    def backfill_upgrade_memory_records(self, records: list[Any]) -> None:
        self._internal_service.backfill_upgrade_memory_records(records)

    def ingest_upgrade_memory_record(self, record: Any, *, skip_seen_check: bool = False) -> None:
        self._internal_service.ingest_upgrade_memory_record(record, skip_seen_check=skip_seen_check)

    def _ensure_consolidation_stack(self) -> tuple[Any, Any]:
        engine = getattr(self._internal_service, "consolidation_engine", None)
        bridge = self._consolidation_bridge
        if engine is not None and bridge is not None:
            return engine, bridge

        with self._consolidation_lock:
            engine = getattr(self._internal_service, "consolidation_engine", None)
            bridge = self._consolidation_bridge
            if engine is not None and bridge is not None:
                return engine, bridge

            engine = self._build_consolidation_engine()
            from zentex.memory.consolidation.bridge import ConsolidationToEnhancedBridge

            bridge = ConsolidationToEnhancedBridge(
                engine=engine,
                enhanced_service=self._internal_service,
            )
            self._internal_service.consolidation_engine = engine
            self._consolidation_bridge = bridge
            return engine, bridge

    def _build_consolidation_engine(self) -> Any:
        from zentex.kernel import get_service as get_kernel_service
        from zentex.kernel.public import BrainTranscriptStore
        from zentex.llm import get_llm_service
        from zentex.memory.consolidation.consolidation import (
            ConsolidationEngine,
            ReflectionClusteringPlugin,
        )
        from zentex.memory.consolidation.semantic_clusterer import SemanticClusteringPlugin
        from zentex.plugins.contracts import PluginLifecycleStatus
        from zentex.plugins.service import get_service as get_plugin_service

        transcript_store = None
        try:
            transcript_store = getattr(get_kernel_service(), "transcript_store", None)
        except Exception:
            logger.warning("Failed to resolve kernel transcript store for memory consolidation", exc_info=True)
        if transcript_store is None:
            transcript_store = BrainTranscriptStore(self.storage_root / "consolidation_transcript.sqlite3")

        analysis_plugins: list[Any] = []
        try:
            plugin_service = get_plugin_service()
            plugin_service.register_discovered_plugins()
            plugin_service.rehydrate_registered_plugins()
            active_rows = plugin_service.query_plugins_by_lifecycle(
                lifecycle_status="active",
                behavior_key="memory_consolidation",
                limit=200,
            )
            for row in active_rows:
                plugin_id = str(row.get("plugin_id") or "").strip()
                if not plugin_id:
                    continue
                plugin = plugin_service.get_plugin(plugin_id)
                if plugin is not None:
                    if not hasattr(plugin, "status"):
                        setattr(
                            plugin,
                            "status",
                            getattr(plugin, "lifecycle_status", PluginLifecycleStatus.ACTIVE),
                        )
                    analysis_plugins.append(plugin)
        except Exception:
            logger.warning("Failed to resolve runtime memory consolidation plugins", exc_info=True)

        if not analysis_plugins:
            try:
                semantic_plugin = SemanticClusteringPlugin()
                semantic_plugin.status = PluginLifecycleStatus.ACTIVE
                analysis_plugins.append(semantic_plugin)
            except Exception:
                logger.warning("Failed to initialize SemanticClusteringPlugin; falling back", exc_info=True)
            fallback_plugin = ReflectionClusteringPlugin()
            fallback_plugin.status = PluginLifecycleStatus.ACTIVE
            analysis_plugins.append(fallback_plugin)

        return ConsolidationEngine(
            llm_service=get_llm_service(),
            analysis_plugins=analysis_plugins,
            transcript_store=transcript_store,
            brain_scope=f"memory-service:{self.storage_root}",
        )

    def _attach_consolidation_bridge(self, *, future: Any, bridge: Any) -> None:
        def _on_complete(completed_future: Any) -> None:
            try:
                cycle = completed_future.result()
                bridge.process_consolidation_results(cycle)
            except Exception:
                logger.warning("Failed to process consolidation cycle results through memory service", exc_info=True)

        if callable(getattr(future, "add_done_callback", None)):
            future.add_done_callback(_on_complete)

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic information about the memory service."""
        health_snapshot = self._internal_service.get_health_snapshot()
        return {
            "storage_root": str(self.storage_root),
            "backend_status": [b.model_dump() for b in self._internal_service.get_backend_status()],
            "health_status": health_snapshot["health_status"],
            "health_snapshot": health_snapshot,
            "projection_failures": self._internal_service.list_projection_failures(),
            "initialization_failures": self._internal_service.list_initialization_failures(),
            "governance_failures": self._internal_service.list_governance_failures(),
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
