from __future__ import annotations
"""
ZMSP Sync Engine: Memory synchronization between Zentex instances.

Handles push/pull/conflict resolution for distributed memory sharing.
"""


import asyncio
import logging
from typing import List, Dict, Optional, Callable
from datetime import datetime, timezone

import httpx

from zentex.memory.sharing.zmsp import ZMSPEncoder, ZMSPDecoder

logger = logging.getLogger(__name__)


class SyncConflict:
    """Represents a memory conflict between instances."""
    
    def __init__(self, memory_id: str, version_a: dict, version_b: dict):
        self.memory_id = memory_id
        self.version_a = version_a
        self.version_b = version_b
        self.timestamp_a = version_a.get("created_at", "")
        self.timestamp_b = version_b.get("created_at", "")
    
    def resolve_auto(self) -> dict:
        """Auto-resolve by taking latest timestamp."""
        if self.timestamp_a >= self.timestamp_b:
            return self.version_a
        return self.version_b


class SyncEngine:
    """
    Manages memory synchronization between Zentex instances.
    
    Usage:
        engine = SyncEngine(aes_key=shared_key)
        await engine.push("https://remote.example.com/sync", records)
    """
    
    def __init__(
        self,
        aes_key: Optional[bytes] = None,
        timeout: float = 30.0,
        batch_size: int = 100
    ):
        self.aes_key = aes_key
        self.timeout = timeout
        self.batch_size = batch_size
        self._client = httpx.AsyncClient(timeout=timeout)
        
        # Conflict resolution callback (can be customized)
        self._conflict_resolver: Optional[Callable[[SyncConflict], dict]] = None
    
    async def close(self):
        await self._client.aclose()
    
    def set_conflict_resolver(self, resolver: Callable[[SyncConflict], dict]):
        """Set custom conflict resolution strategy."""
        self._conflict_resolver = resolver
    
    async def push(
        self,
        target_url: str,
        records: List[dict],
        require_ack: bool = True
    ) -> Dict[str, any]:
        """
        Push memory records to remote instance.
        
        Args:
            target_url: Remote sync endpoint (e.g., "https://remote/sync/push")
            records: List of EnhancedMemoryRecord dicts
            require_ack: Wait for acknowledgment
            
        Returns:
            Response metadata
        """
        logger.info(f"Pushing {len(records)} records to {target_url}")
        
        # Encode in batches
        encoder = ZMSPEncoder(aes_key=self.aes_key, compress=True)
        
        total_sent = 0
        errors = []
        
        for i in range(0, len(records), self.batch_size):
            batch = records[i:i + self.batch_size]
            
            try:
                binary = encoder.encode(batch)
                
                headers = {"Content-Type": "application/octet-stream"}
                if require_ack:
                    headers["X-ZMSP-Require-Ack"] = "true"
                
                response = await self._client.post(
                    target_url,
                    content=binary,
                    headers=headers
                )
                
                if response.status_code == 200:
                    total_sent += len(batch)
                    logger.debug(f"Batch {i//self.batch_size + 1} sent successfully")
                else:
                    errors.append({
                        "batch": i // self.batch_size,
                        "status": response.status_code,
                        "error": response.text
                    })
                    
            except Exception as e:
                logger.error(f"Failed to send batch {i//self.batch_size}: {e}")
                errors.append({
                    "batch": i // self.batch_size,
                    "error": str(e)
                })
        
        result = {
            "total_records": len(records),
            "sent": total_sent,
            "failed": len(errors),
            "errors": errors
        }
        
        logger.info(f"Push complete: {total_sent}/{len(records)} sent")
        return result
    
    async def pull(
        self,
        source_url: str,
        hashes: List[str]
    ) -> List[dict]:
        """
        Pull missing memory records from remote instance.
        
        Args:
            source_url: Remote sync endpoint (e.g., "https://remote/sync/pull")
            hashes: List of content hashes to fetch
            
        Returns:
            List of fetched records
        """
        logger.info(f"Pulling {len(hashes)} records from {source_url}")
        
        response = await self._client.post(
            source_url,
            json={"hashes": hashes}
        )
        
        if response.status_code != 200:
            raise Exception(f"Pull failed: {response.status_code} {response.text}")
        
        # Decode ZMSP binary
        decoder = ZMSPDecoder(aes_key=self.aes_key)
        records, metadata = decoder.decode(response.content)
        
        logger.info(f"Pulled {len(records)} records")
        return records
    
    async def sync_bidirectional(
        self,
        remote_url: str,
        local_records: List[dict],
        local_hashes: set
    ) -> Dict[str, any]:
        """
        Perform bidirectional sync with remote instance.
        
        Flow:
        1. Push local records to remote
        2. Get remote's hash list
        3. Pull missing records from remote
        4. Resolve conflicts
        
        Args:
            remote_url: Remote sync endpoint
            local_records: Local records to push
            local_hashes: Set of local content hashes
            
        Returns:
            Sync result summary
        """
        logger.info(f"Starting bidirectional sync with {remote_url}")
        
        # Step 1: Push local records
        push_result = await self.push(f"{remote_url}/push", local_records)
        
        # Step 2: Get remote hashes
        response = await self._client.get(f"{remote_url}/hashes")
        if response.status_code != 200:
            raise Exception(f"Failed to get remote hashes: {response.status_code}")
        
        remote_hashes = set(response.json()["hashes"])
        
        # Step 3: Determine missing records
        missing_hashes = remote_hashes - local_hashes
        
        # Step 4: Pull missing records
        pulled_records = []
        if missing_hashes:
            pulled_records = await self.pull(f"{remote_url}/pull", list(missing_hashes))
        
        # Step 5: Detect conflicts (records with same ID but different hash)
        conflicts = await self._detect_conflicts(remote_url, local_records)
        
        result = {
            "pushed": push_result["sent"],
            "pulled": len(pulled_records),
            "conflicts": len(conflicts),
            "resolved_conflicts": []
        }
        
        # Step 6: Resolve conflicts
        for conflict in conflicts:
            if self._conflict_resolver:
                resolved = self._conflict_resolver(conflict)
            else:
                resolved = conflict.resolve_auto()
            result["resolved_conflicts"].append(resolved)
        
        logger.info(f"Sync complete: {result}")
        return result
    
    async def _detect_conflicts(
        self,
        remote_url: str,
        local_records: List[dict]
    ) -> List[SyncConflict]:
        """Detect memory conflicts between local and remote."""
        conflicts = []
        
        # Build local index: memory_id -> record
        local_index = {rec["memory_id"]: rec for rec in local_records}
        
        # Check each local record against remote
        for memory_id, local_rec in local_index.items():
            # Query remote for this record
            response = await self._client.get(f"{remote_url}/record/{memory_id}")
            
            if response.status_code == 200:
                remote_rec = response.json()
                
                # Compare content hashes
                if remote_rec.get("content_hash") != local_rec.get("content_hash"):
                    conflict = SyncConflict(memory_id, local_rec, remote_rec)
                    conflicts.append(conflict)
        
        return conflicts
    
    async def health_check(self, remote_url: str) -> bool:
        """Check if remote instance is reachable."""
        try:
            response = await self._client.get(f"{remote_url}/health")
            return response.status_code == 200
        except Exception:
            # POLICY[no-silent-except]: probe failure is expected when remote is down; log at DEBUG.
            logger.debug("Health check failed for remote %s", remote_url, exc_info=True)
            return False


class SyncScheduler:
    """
    Automatic synchronization scheduler.
    
    Periodically syncs memory between instances based on:
    - Time interval
    - Record count threshold
    - Manual trigger
    """
    
    def __init__(
        self,
        sync_engine: SyncEngine,
        interval_seconds: int = 300,  # 5 minutes
        max_batch_size: int = 100
    ):
        self.sync_engine = sync_engine
        self.interval = interval_seconds
        self.max_batch_size = max_batch_size
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self, remote_url: str, get_local_records: Callable):
        """
        Start automatic sync loop.
        
        Args:
            remote_url: Remote sync endpoint
            get_local_records: Callback that returns (records, hashes) tuple
        """
        self._running = True
        self._task = asyncio.create_task(
            self._sync_loop(remote_url, get_local_records)
        )
        logger.info(f"Sync scheduler started (interval={self.interval}s)")
    
    async def stop(self):
        """Stop automatic sync loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("Sync scheduler task cancellation completed", exc_info=True)
        logger.info("Sync scheduler stopped")
    
    async def _sync_loop(self, remote_url: str, get_local_records: Callable):
        """Main sync loop."""
        while self._running:
            try:
                # Check remote health
                if not await self.sync_engine.health_check(remote_url):
                    logger.warning("Remote instance unreachable, skipping sync")
                    await asyncio.sleep(self.interval)
                    continue
                
                # Get local records
                records, hashes = get_local_records()
                
                if len(records) > self.max_batch_size:
                    logger.warning(
                        f"Too many records ({len(records)}), limiting to {self.max_batch_size}"
                    )
                    records = records[:self.max_batch_size]
                
                # Perform sync
                if records:
                    await self.sync_engine.sync_bidirectional(
                        remote_url,
                        records,
                        hashes
                    )
                
            except Exception as e:
                logger.error(f"Sync loop error: {e}", exc_info=True)
            
            # Wait for next iteration
            await asyncio.sleep(self.interval)


# Convenience functions for integration

def create_sync_client(
    remote_url: str,
    aes_key: bytes,
    auto_sync: bool = False,
    sync_interval: int = 300
) -> SyncEngine:
    """
    Create and configure a sync client.
    
    Args:
        remote_url: Remote instance URL
        aes_key: Shared encryption key
        auto_sync: Enable automatic sync
        sync_interval: Auto-sync interval in seconds
        
    Returns:
        Configured SyncEngine
    """
    engine = SyncEngine(aes_key=aes_key)
    
    if auto_sync:
        scheduler = SyncScheduler(engine, interval_seconds=sync_interval)
        # Scheduler needs to be started separately with proper callbacks
        engine.scheduler = scheduler
    
    return engine


if __name__ == "__main__":
    # Demo usage
    import asyncio
    
    async def demo():
        # Create sync engine
        aes_key = b"\x00" * 32  # In production, use secure key generation
        engine = SyncEngine(aes_key=aes_key)
        
        # Sample records
        records = [
            {
                "memory_id": "550e8400-e29b-41d4-a716-446655440000",
                "memory_layer": "semantic",
                "source_kind": "transcript",
                "title": "Test Memory",
                "summary": "Test summary",
                "content": "Test content",
                "trace_id": "trace-123",
                "memory_tier": "hot",
                "emotional_valence": "neutral",
                "affect_intensity": 0.5,
                "confidence_score": 0.8,
                "verification_status": "unverified",
                "created_at": "2026-04-08T12:00:00+00:00"
            }
        ]
        
        # Note: This will fail without a real remote server
        # It's just showing the API usage
        try:
            result = await engine.push("http://localhost:8000/sync/push", records)
            print(f"Push result: {result}")
        except Exception as e:
            print(f"Expected error (no server): {e}")
        
        await engine.close()
    
    asyncio.run(demo())
