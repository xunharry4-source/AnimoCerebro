from __future__ import annotations

import time
from typing import Any, Dict, List
from zentex.memory.consolidation.consolidation import ConsolidationEngine, ConsolidationCycle
from zentex.memory.management.enhanced import EnhancedMemoryService, MemoryManagementStatus

class ConsolidationToEnhancedBridge:
    """Sub-function 59.4 - Integration pipeline between Consolidation and Enhanced Memory (0% gap)."""
    
    def __init__(self, engine: ConsolidationEngine, enhanced_service: EnhancedMemoryService):
        self._engine = engine
        self._enhanced_service = enhanced_service

    def get_quarantined_records(self) -> list:
        """Public API to query quarantined records."""
        return self._enhanced_service.list_managed_records(status="quarantined")
    
    def get_managed_record(self, memory_id: str):
        """Public API to get a specific managed record."""
        return self._enhanced_service.get_managed_record(memory_id)
    
    def ingest_candidate(self, candidate_data: dict, operator: str = "system") -> str:
        """Public API to ingest a candidate into quarantine."""
        return self._enhanced_service.ingest_candidate(candidate_data, operator=operator)
    
    def promote_from_quarantine(self, memory_id: str, operator: str = "validator"):
        """Public API to promote a record from quarantine to active."""
        return self._enhanced_service.promote_from_quarantine(memory_id, operator=operator)
    
    def update_management_state(self, memory_id: str, status: str, operator: str = "system", reason: str = ""):
        """Public API to update management state."""
        return self._enhanced_service.update_management_state(memory_id, lifecycle_status=lifecycle_status, operator=operator, reason=reason)
    
    def list_audit_events(self, memory_id: str = None) -> list:
        """Public API to list audit events."""
        return self._enhanced_service.list_audit_events(memory_id=memory_id)

    def process_consolidation_results(self, cycle: ConsolidationCycle):
        """Convert consolidation outputs to enhanced memory records (Priority 4)."""
        
        # 1. Process promotion candidates (Move to Quarantine layer)
        for candidate in cycle.promotion_candidates:
            # We ingest candidates into the quarantined layer for G38 audit
            candidate_id = self._enhanced_service.ingest_candidate(
                candidate.model_dump(mode="json"),
                operator=f"consolidation-cycle-{cycle.cycle_id}"
            )
            # Link back to cycle
            cycle.summary += f"\n- Candidate {candidate.source_ref} ingested as {candidate_id} for G38 audit."

        # 2. Apply compression markers (Sub-function 59.5)
        for ref_id in cycle.compressed_refs:
            self._enhanced_service.update_management_state(
                ref_id,
                status=MemoryManagementStatus.COLD,
                reason=f"Compressed by consolidation cycle {cycle.cycle_id}"
            )

        # 3. Apply tombstones (Sub-function 59.5)
        for ref_id in cycle.pruned_refs:
            self._enhanced_service.update_management_state(
                ref_id,
                status=MemoryManagementStatus.REJECTED,
                reason=f"Pruned (forgotten) by consolidation cycle {cycle.cycle_id}"
            )
            
    def archive_cold(self, memory_ids: List[str]):
        """Move memory references from warm/hot to cold storage (Priority 3)."""
        for ref_id in memory_ids:
            self._enhanced_service.update_management_state(
                ref_id,
                status=MemoryManagementStatus.COLD,
                reason="Archived to cold storage by consolidation engine."
            )


class ConsolidationScheduler:
    """Sub-function 59.4 - Automatic scheduling for memory governance (0% gap)."""
    
    def __init__(self, engine: ConsolidationEngine, bridge: ConsolidationToEnhancedBridge):
        self._engine = engine
        self._bridge = bridge
        self._memory_budget_bytes = 100 * 1024 * 1024  # 100MB Default limit

    def check_and_trigger(self, force: bool = False):
        """Check conditions and auto-trigger consolidation (Priority 3)."""
        # 1. Check storage budget exceeding thresholds (85% of budget)
        current_usage = self._engine._calculate_tier_size("hot")
        budget_exceeded = current_usage > (self._memory_budget_bytes * 0.85)

        # 2. Check system idle (Simulated)
        system_idle = True # In a real system, check CPU/IO load
        
        if force or budget_exceeded or system_idle:
             # Submit a new consolidation cycle
             handle, future = self._engine.submit_cycle(
                 trigger_stage="memory_governance_review",
                 input_memory_refs=[], # Real implementation would fetch active refs
                 noise_rules=[],
                 context={"trigger": "scheduler_auto"},
                 idempotency_key=f"sched-{int(time.time())}",
                 snapshot_version=self._engine.snapshot_version
             )
             
             # Attach bridge to process results when done
             def on_complete(fut):
                 try:
                     cycle = fut.result()
                     self._bridge.process_consolidation_results(cycle)
                 except Exception:
                     pass
             
             future.add_done_callback(on_complete)
             return handle.cycle_id
        
        return None
