from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException
from typing_extensions import Annotated
from fastapi import Depends

from zentex.cognition.simulation import CounterfactualSimulationEngine
from zentex.cognition.social_mind import InteractionMindEngine
from zentex.memory import ConsolidationEngine
from zentex.runtime.temporal import CognitiveTemporalEngine
from zentex.safety.conflict_engine import CognitiveConflictEngine
from zentex.web_console.contracts.runtime import (
    CognitiveAgendaPayload,
    CognitiveConflictPayload,
    ConsolidationCyclesPayload,
    InteractionMindPayload,
    SimulationBundlePayload,
)
from zentex.web_console.dependencies import (
    get_conflict_engine,
    get_consolidation_engine,
    get_interaction_mind_engine,
    get_simulation_engine,
    get_temporal_engine,
)


router = APIRouter()


@router.get("/cognitive-agenda", response_model=CognitiveAgendaPayload)
def get_cognitive_agenda(
    temporal_engine: Annotated[CognitiveTemporalEngine, Depends(get_temporal_engine)],
) -> CognitiveAgendaPayload:
    state = temporal_engine.evaluate()
    return CognitiveAgendaPayload(
        state=state.model_dump(mode="json"),
        items=[item.model_dump(mode="json") for item in state.items],
    )


@router.get("/cognitive-conflicts", response_model=CognitiveConflictPayload)
def get_cognitive_conflicts(
    conflict_engine: Annotated[CognitiveConflictEngine, Depends(get_conflict_engine)],
) -> CognitiveConflictPayload:
    snapshot_fn = getattr(conflict_engine, "snapshot", None)
    if not callable(snapshot_fn):
        raise HTTPException(
            status_code=500,
            detail=(
                "CognitiveConflictEngine is missing snapshot() implementation; "
                "backend assembly is incompatible with the web console contract."
            ),
        )
    report = snapshot_fn()
    report_payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else {}
    conflicts = report_payload.get("unresolved_conflicts", [])
    if not isinstance(conflicts, list):
        conflicts = []
    snapshot_version = report_payload.get("snapshot_version", 0)
    try:
        snapshot_version = int(snapshot_version)
    except Exception:
        snapshot_version = 0
    brain_scope = report_payload.get("brain_scope")
    brain_scope = str(brain_scope) if brain_scope is not None else None
    return CognitiveConflictPayload(
        conflicts=conflicts,
        snapshot_version=snapshot_version,
        brain_scope=brain_scope,
    )


@router.get("/simulations/{goal_id}", response_model=SimulationBundlePayload)
def get_simulation_bundle(
    goal_id: str,
    simulation_engine: Annotated[CounterfactualSimulationEngine, Depends(get_simulation_engine)],
) -> SimulationBundlePayload:
    if simulation_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Simulation engine is not available.",
        )
    try:
        bundle = simulation_engine.get_bundle(goal_id)
        if bundle is None:
            raise HTTPException(
                status_code=404,
                detail=f"Simulation bundle not found for goal_id: {goal_id}",
            )
        bundle_payload = bundle.model_dump(mode="json") if hasattr(bundle, "model_dump") else {}
        return SimulationBundlePayload(bundle=bundle_payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve simulation bundle: {exc}",
        ) from exc


@router.get("/interaction-mind/{entity_id}", response_model=InteractionMindPayload)
def get_interaction_mind(
    entity_id: str,
    interaction_mind_engine: Annotated[InteractionMindEngine, Depends(get_interaction_mind_engine)],
) -> InteractionMindPayload:
    state = interaction_mind_engine.get_state(entity_id)
    state_payload = state.model_dump(mode="json") if hasattr(state, "model_dump") else {}
    return InteractionMindPayload(state=state_payload)


@router.get("/memory/consolidation-cycles", response_model=ConsolidationCyclesPayload)
def get_consolidation_cycles(
    consolidation_engine: Annotated[ConsolidationEngine, Depends(get_consolidation_engine)],
) -> ConsolidationCyclesPayload:
    cycles = consolidation_engine.get_recent_cycles()
    return ConsolidationCyclesPayload(
        cycles=[cycle.model_dump(mode="json") if hasattr(cycle, "model_dump") else {} for cycle in cycles]
    )


@router.post("/memory/consolidation/trigger")
def trigger_consolidation(
    consolidation_engine: Annotated[ConsolidationEngine, Depends(get_consolidation_engine)],
) -> dict[str, str]:
    """Manual trigger for memory consolidation via Web Console (Sub-function 59 gap)."""
    cycle_id = consolidation_engine.submit_cycle(trigger_reason="manual_web_console")
    return {"status": "triggered", "cycle_id": cycle_id}
