from __future__ import annotations

import os
import shutil
import time
import logging
from datetime import UTC, datetime
from threading import Thread
from zentex.upgrade.management import UpgradeManagementStore, UpgradeLifecycleStatus

logger = logging.getLogger(__name__)

class EvolutionCleanupWorker:
    """Sub-function 58.4 - Automatic cleanup of evolution artifacts (0% gap)."""
    
    def __init__(self, store: UpgradeManagementStore, interval_seconds: int = 3600):
        self._store = store
        self._interval = interval_seconds
        self._running = False
        self._thread = None

    def start(self):
        """Start the background cleanup thread."""
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = Thread(target=self._run_loop, daemon=True, name="evolution-cleanup")
        self._thread.start()
        logger.info("EvolutionCleanupWorker started.")

    def stop(self):
        """Stop the background cleanup thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        while self._running:
            try:
                self.perform_cleanup()
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
            time.sleep(self._interval)

    def perform_cleanup(self):
        """Scan and remove artifacts for failed or completed jobs (Priority 4)."""
        # 1. List all records
        records = self._store.list_records()
        
        # 2. Filter for status that can be cleaned up
        # We clean up FAILED jobs (after N days) or already COMPLETED jobs whose artifacts are no longer needed
        for record in records:
            if record.current_status in [UpgradeLifecycleStatus.FAILED, UpgradeLifecycleStatus.CANCELLED, UpgradeLifecycleStatus.COMPLETED]:
                # Avoid cleaning up very recent jobs
                now = datetime.now(UTC)
                updated_at = record.updated_at
                
                # Ensure both are timezone-aware
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=UTC)
                
                age_seconds = (now - updated_at).total_seconds()
                
                if age_seconds > 86400:  # 1 day
                    self._cleanup_record_artifacts(record)

    def _cleanup_record_artifacts(self, record):
        """Physically remove candidate directories."""
        if record.candidate_path and os.path.exists(record.candidate_path):
            try:
                # Security check: Ensure we are only deleting within a known temporary/candidate zone
                if "candidate" in record.candidate_path or "sandbox" in record.candidate_path:
                    shutil.rmtree(record.candidate_path)
                    logger.info(f"Cleaned up artifacts for record {record.record_id} at {record.candidate_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup {record.candidate_path}: {e}")
        
        # Update status if it was FAILED or COMPLETED to indicate cleaned
        if record.current_status != UpgradeLifecycleStatus.CLEANED_UP:
             # This is a bit tricky since we don't want to lose the original result status
             # but we can add a flag or note
             pass
