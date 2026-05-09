from __future__ import annotations
"""
Cognition Route Handlers — Business logic for cognitive engine interactions.
Extracted from cognition.py to follow the Facade-First / Thin-Route pattern.
"""
import logging
from typing import Any, Dict, List
from fastapi import HTTPException
from zentex.web_console.contracts.runtime import (
    CognitiveAgendaPayload,
    CognitiveConflictPayload,
    ConsolidationCyclesPayload,
    InteractionMindPayload,
    SimulationBundlePayload,
)

logger = logging.getLogger(__name__)


def handle_get_cognitive_agenda(temporal_engine: Any) -> CognitiveAgendaPayload:
    """Handle retrieving the cognitive agenda state."""
    if temporal_engine is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "temporal_engine_unavailable",
                "message": "CognitiveTemporalEngine 未初始化，runtime 未注入 app.state。",
            },
        )
    try:
        snap = temporal_engine.snapshot()
        return CognitiveAgendaPayload(
            state={
                "state_id": snap.get("session_id", "temporal"),
                "review_now_item_ids": [],
                "overdue_item_ids": [],
                **snap,
            },
            items=[],
        )
    except TimeoutError:
        logger.warning("CognitiveTemporalEngine.evaluate() timed out; returning empty agenda")
        return CognitiveAgendaPayload(
            state={
                "state_id": "timeout_fallback",
                "review_now_item_ids": [],
                "overdue_item_ids": [],
                "health_status": "degraded",
                "degradation_reason": "timeout",
            },
            items=[],
        )
    except Exception:
        # Do not collapse agenda engine faults into a silent empty agenda. The
        # monitoring page may degrade to an empty list, but it must explicitly show
        # degraded state and preserve the traceback for diagnosis.
        logger.exception("Error evaluating cognitive agenda")
        return CognitiveAgendaPayload(
            state={
                "state_id": "error_fallback",
                "review_now_item_ids": [],
                "overdue_item_ids": [],
                "health_status": "degraded",
                "degradation_reason": "exception",
            },
            items=[],
        )


def handle_get_cognitive_conflicts(conflict_engine: Any) -> CognitiveConflictPayload:
    """Handle retrieving unresolved cognitive conflicts."""
    if conflict_engine is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "conflict_engine_unavailable",
                "message": "CognitiveConflictEngine 未初始化，runtime 未注入 app.state。",
            },
        )
    
    snapshot_fn = getattr(conflict_engine, "snapshot", None)
    if not callable(snapshot_fn):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "conflict_engine_contract_mismatch",
                "message": "CognitiveConflictEngine 缺少 snapshot() 实现。",
            },
        )
        
    report = snapshot_fn()
    report_payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else {}
    conflicts = report_payload.get("unresolved_conflicts", [])
    if not isinstance(conflicts, list):
        conflicts = []
        
    return CognitiveConflictPayload(
        conflicts=conflicts,
        snapshot_version=int(report_payload.get("snapshot_version", 0)),
        brain_scope=str(report_payload.get("brain_scope", "")) if report_payload.get("brain_scope") else None,
    )


def handle_get_simulation_bundle(goal_id: str, simulation_engine: Any) -> SimulationBundlePayload:
    """Handle retrieving a counterfactual simulation bundle."""
    if simulation_engine is None:
        raise HTTPException(status_code=503, detail="Simulation engine is not available.")
        
    try:
        bundle = simulation_engine.get_bundle(goal_id)
        if bundle is None:
            raise HTTPException(status_code=404, detail=f"Simulation bundle not found for goal_id: {goal_id}")
            
        bundle_payload = bundle.model_dump(mode="json") if hasattr(bundle, "model_dump") else {}
        return SimulationBundlePayload(bundle=bundle_payload)
    except HTTPException:
        raise
    except Exception as exc:
        # Do not hide simulation retrieval failures behind a plain 500 without a
        # traceback. That would make the control surface look healthy while the
        # backend bundle assembly is already broken.
        logger.exception("Error retrieving simulation bundle for %s", goal_id)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve simulation bundle: {exc}")


def handle_get_interaction_mind(entity_id: str, interaction_mind_engine: Any) -> InteractionMindPayload:
    """Handle retrieving the interaction mind state for an entity."""
    if interaction_mind_engine is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "interaction_mind_engine_unavailable",
                "message": "InteractionMindEngine 未初始化。",
            },
        )
    try:
        state = interaction_mind_engine.get_state(entity_id)
        state_payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else {}
        return InteractionMindPayload(state=state_payload)
    except HTTPException:
        raise
    except Exception as exc:
        # Do not let interaction-mind retrieval fail without an explicit traceback.
        # Pretending this is a generic backend miss destroys operational visibility.
        logger.exception("Error retrieving interaction mind for %s", entity_id)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "interaction_mind_query_failed",
                "message": "Failed to retrieve interaction mind state",
                "entity_id": entity_id,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


def handle_get_consolidation_cycles(consolidation_engine: Any) -> ConsolidationCyclesPayload:
    """Handle retrieving recent memory consolidation cycles."""
    if consolidation_engine is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "consolidation_engine_unavailable",
                "message": "ConsolidationEngine 未初始化。",
            },
        )
    try:
        cycles = consolidation_engine.get_recent_cycles()
        return ConsolidationCyclesPayload(
            cycles=[cycle.model_dump(mode="json") if hasattr(cycle, "model_dump") else {} for cycle in cycles]
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error retrieving consolidation cycles")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "consolidation_cycles_query_failed",
                "message": "Failed to retrieve consolidation cycles",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc


def handle_trigger_consolidation(consolidation_engine: Any) -> Dict[str, Any]:
    """Handle manual trigger for memory consolidation."""
    if consolidation_engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "consolidation_engine_unavailable"},
        )
    try:
        handle = consolidation_engine.submit_manual_trigger(operator="web_console")
        queried = consolidation_engine.list_cycles(cycle_id=handle.cycle_id)
        if not queried:
            raise RuntimeError(f"Consolidation read-after-write failed for cycle {handle.cycle_id}")
        return {
            "status": "triggered",
            "cycle_id": handle.cycle_id,
            "lease_id": handle.lease_id,
            "idempotency_key": handle.idempotency_key,
            "snapshot_version": handle.snapshot_version,
            "queued_cycle": queried[0].model_dump(mode="json") if hasattr(queried[0], "model_dump") else {},
        }
    except HTTPException:
        raise
    except Exception as exc:
        # Manual trigger is a control path. Returning a generic failure without the
        # traceback would hide a real backend control-plane fault and is forbidden.
        logger.exception("Error triggering consolidation cycle from cognition handler")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "consolidation_trigger_failed",
                "message": "Failed to trigger consolidation cycle",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        ) from exc
