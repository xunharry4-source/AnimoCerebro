"""
ZMSP Bridge: Integration between ZMSP protocol and EnhancedMemoryService.

Provides seamless export/import of memory records using ZMSP binary format.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from pathlib import Path

from zentex.memory.sharing.zmsp import ZMSPEncoder, ZMSPDecoder

logger = logging.getLogger(__name__)


class ZMSPBridge:
    """
    Bridge between EnhancedMemoryService and ZMSP protocol.
    
    Usage:
        bridge = ZMSPBridge(enhanced_service, aes_key=shared_key)
        
        # Export memories
        binary_package = bridge.export_records(layer="semantic", limit=100)
        
        # Import memories
        bridge.import_package(binary_package, origin="remote-instance")
    """
    
    def __init__(
        self,
        enhanced_service,  # EnhancedMemoryService instance
        aes_key: Optional[bytes] = None
    ):
        self.service = enhanced_service
        self.aes_key = aes_key
    
    def export_records(
        self,
        layer: str = "all",
        limit: int = 100,
        status: Optional[str] = None,
        trust_level: Optional[str] = None
    ) -> bytes:
        """
        Export memory records to ZMSP binary format.
        
        Args:
            layer: Memory layer (semantic/procedural/episodic/all)
            limit: Maximum number of records to export
            status: Filter by status (active/deprecated/archived)
            trust_level: Filter by trust level
            
        Returns:
            Binary ZMSP frame
        """
        logger.info(f"Exporting up to {limit} records from layer '{layer}'")
        
        # Fetch records from EnhancedMemoryService
        records = self.service.list_managed_records(
            layer=layer,
            limit=limit,
            lifecycle_status=lifecycle_status,
            trust_level=trust_level
        )
        
        if not records:
            logger.warning("No records found for export")
            return b""
        
        # Convert to dict format
        record_dicts = [rec.model_dump() for rec in records]
        
        # Encode to ZMSP
        encoder = ZMSPEncoder(aes_key=self.aes_key, compress=True)
        binary = encoder.encode(record_dicts)
        
        logger.info(f"Exported {len(records)} records ({len(binary)} bytes)")
        return binary
    
    def export_to_file(
        self,
        file_path: str | Path,
        layer: str = "all",
        limit: int = 100
    ) -> Path:
        """
        Export memory records to ZMSP binary file.
        
        Args:
            file_path: Output file path
            layer: Memory layer
            limit: Maximum records
            
        Returns:
            Path to exported file
        """
        binary = self.export_records(layer=layer, limit=limit)
        
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(binary)
        
        logger.info(f"Exported to {path} ({len(binary)} bytes)")
        return path
    
    def import_package(
        self,
        binary_data: bytes,
        origin: str = "unknown",
        skip_duplicates: bool = True
    ) -> Tuple[int, int]:
        """
        Import memory records from ZMSP binary package.
        
        Args:
            binary_data: Binary ZMSP frame
            origin: Source identifier (for audit trail)
            skip_duplicates: Skip records with existing content_hash
            
        Returns:
            (imported_count, skipped_count)
        """
        logger.info(f"Importing package from '{origin}' ({len(binary_data)} bytes)")
        
        # Decode ZMSP
        decoder = ZMSPDecoder(aes_key=self.aes_key)
        try:
            records, metadata = decoder.decode(binary_data)
        except Exception as e:
            logger.error(f"Failed to decode ZMSP package: {e}")
            raise
        
        logger.info(f"Decoded {len(records)} records (compressed={metadata['compressed']}, encrypted={metadata['encrypted']})")
        
        # Get existing hashes for deduplication
        existing_hashes = set()
        if skip_duplicates:
            all_records = self.service.list_managed_records(limit=10000)
            existing_hashes = {rec.content_hash for rec in all_records if rec.content_hash}
        
        # Import records
        imported = 0
        skipped = 0
        
        for rec_dict in records:
            # Check for duplicates
            if skip_duplicates and rec_dict.get("content_hash") in existing_hashes:
                skipped += 1
                continue
            
            try:
                # Import into EnhancedMemoryService
                # Note: This requires adding an import method to EnhancedMemoryService
                self._import_single_record(rec_dict, origin)
                imported += 1
                
                # Add to existing hashes to avoid duplicates within same package
                if rec_dict.get("content_hash"):
                    existing_hashes.add(rec_dict["content_hash"])
                    
            except Exception as e:
                logger.error(f"Failed to import record {rec_dict.get('memory_id')}: {e}")
                skipped += 1
        
        logger.info(f"Import complete: {imported} imported, {skipped} skipped")
        return imported, skipped
    
    def import_from_file(
        self,
        file_path: str | Path,
        origin: Optional[str] = None
    ) -> Tuple[int, int]:
        """
        Import memory records from ZMSP binary file.
        
        Args:
            file_path: Input file path
            origin: Source identifier (defaults to filename)
            
        Returns:
            (imported_count, skipped_count)
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Package file not found: {path}")
        
        if origin is None:
            origin = path.stem
        
        binary_data = path.read_bytes()
        return self.import_package(binary_data, origin=origin)
    
    def _import_single_record(self, rec_dict: dict, origin: str):
        """
        Import a single memory record into EnhancedMemoryService.
        
        This is a placeholder - actual implementation depends on
        EnhancedMemoryService API.
        """
        # TODO: Implement actual import logic
        # For now, we'll use the existing store_memory API if available
        
        if hasattr(self.service, 'store_memory'):
            # Try to use store_memory API
            self.service.store_memory(
                title=rec_dict.get("title", "Imported Memory"),
                summary=rec_dict.get("summary", ""),
                content=rec_dict.get("content", ""),
                layer=rec_dict.get("memory_layer", "semantic"),
                trace_id=rec_dict.get("trace_id", "import"),
                source_kind=rec_dict.get("source_kind", "import"),
                metadata={
                    "import_origin": origin,
                    "import_timestamp": rec_dict.get("created_at"),
                    "confidence": rec_dict.get("confidence_score", 0.5),
                    "valence": rec_dict.get("emotional_valence", "neutral")
                }
            )
        else:
            # Fallback: Direct insertion (not recommended for production)
            logger.warning(
                f"EnhancedMemoryService does not support direct import. "
                f"Record {rec_dict.get('memory_id')} skipped."
            )
            raise NotImplementedError(
                "EnhancedMemoryService needs import_record() method"
            )
    
    def sync_with_remote(
        self,
        remote_url: str,
        batch_size: int = 100
    ) -> dict:
        """
        Perform one-time sync with remote instance.
        
        Args:
            remote_url: Remote sync endpoint
            batch_size: Records per batch
            
        Returns:
            Sync result summary
        """
        from zentex.memory.sharing.sync_engine import SyncEngine
        
        logger.info(f"Starting sync with {remote_url}")
        
        # Create sync engine
        engine = SyncEngine(aes_key=self.aes_key, batch_size=batch_size)
        
        # Get local records
        local_records = self.service.list_managed_records(limit=1000)
        local_hashes = {rec.content_hash for rec in local_records if rec.content_hash}
        
        try:
            # Perform bidirectional sync
            result = engine.sync_bidirectional(
                remote_url,
                [rec.model_dump() for rec in local_records],
                local_hashes
            )
            
            logger.info(f"Sync complete: {result}")
            return result
            
        finally:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(engine.close())
                else:
                    loop.run_until_complete(engine.close())
            except Exception:
                pass


# Convenience function for quick setup

def setup_zmsp_sharing(
    enhanced_service,
    aes_key: bytes,
    remote_url: Optional[str] = None,
    auto_sync: bool = False
) -> ZMSPBridge:
    """
    Setup ZMSP memory sharing for an EnhancedMemoryService instance.
    
    Args:
        enhanced_service: EnhancedMemoryService instance
        aes_key: Shared encryption key (32 bytes)
        remote_url: Optional remote instance URL for sync
        auto_sync: Enable automatic synchronization
        
    Returns:
        Configured ZMSPBridge
    """
    bridge = ZMSPBridge(enhanced_service, aes_key=aes_key)
    
    if remote_url and auto_sync:
        from zentex.memory.sharing.sync_engine import SyncScheduler, SyncEngine
        
        engine = SyncEngine(aes_key=aes_key)
        scheduler = SyncScheduler(engine, interval_seconds=300)
        
        # Start scheduler in background
        import asyncio
        
        async def start_scheduler():
            await scheduler.start(remote_url, lambda: (
                enhanced_service.list_managed_records(limit=100),
                {rec.content_hash for rec in enhanced_service.list_managed_records(limit=10000)}
            ))
        
        # Note: In production, manage this properly with lifecycle
        # asyncio.create_task(start_scheduler())
    
    return bridge


if __name__ == "__main__":
    # Demo usage
    print("ZMSP Bridge module loaded successfully")
    print("\nUsage example:")
    print("""
    from zentex.memory.management.enhanced import EnhancedMemoryService
    from zentex.memory.sharing.bridge import ZMSPBridge
    
    # Initialize services
    service = EnhancedMemoryService(...)
    bridge = ZMSPBridge(service, aes_key=shared_key)
    
    # Export memories
    binary = bridge.export_records(layer="semantic", limit=100)
    
    # Save to file
    bridge.export_to_file("memories.zmsp", layer="semantic")
    
    # Import from file
    imported, skipped = bridge.import_from_file("memories.zmsp", origin="backup")
    print(f"Imported {imported}, skipped {skipped}")
    """)
