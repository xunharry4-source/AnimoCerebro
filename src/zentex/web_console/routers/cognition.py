from __future__ import annotations

from typing import Any
from fastapi import APIRouter
from typing_extensions import Annotated
from fastapi import Depends

from zentex.safety.service import CognitiveConflictEngine
from zentex.web_console.contracts.runtime import (
    CognitiveAgendaPayload,
    CognitiveConflictPayload,
    InteractionMindPayload,
    SimulationBundlePayload,
)
from zentex.web_console.dependencies import (
    get_conflict_engine,
    get_interaction_mind_engine,
    get_simulation_engine,
    get_temporal_engine,
)
from .cognition_handlers import (
    handle_get_cognitive_agenda,
    handle_get_cognitive_conflicts,
    handle_get_interaction_mind,
    handle_get_simulation_bundle,
)


router = APIRouter()


@router.get("/cognitive-agenda", response_model=CognitiveAgendaPayload)
def get_cognitive_agenda(
    temporal_engine: Annotated[Any, Depends(get_temporal_engine)],
) -> CognitiveAgendaPayload:
    # Do not maintain a second cognition implementation in the legacy route layer.
    # Duplicated fallback logic here caused the web path to drift away from the
    # tested handler semantics and created fake-normal behavior in production.
    return handle_get_cognitive_agenda(temporal_engine)


@router.get("/cognitive-conflicts", response_model=CognitiveConflictPayload)
def get_cognitive_conflicts(
    conflict_engine: Annotated[CognitiveConflictEngine, Depends(get_conflict_engine)],
) -> CognitiveConflictPayload:
    return handle_get_cognitive_conflicts(conflict_engine)


@router.get("/simulations/{goal_id}", response_model=SimulationBundlePayload)
def get_simulation_bundle(
    goal_id: str,
    simulation_engine: Annotated[Any, Depends(get_simulation_engine)],
) -> SimulationBundlePayload:
    return handle_get_simulation_bundle(goal_id, simulation_engine)


@router.get("/interaction-mind/{entity_id}", response_model=InteractionMindPayload)
def get_interaction_mind(
    entity_id: str,
    interaction_mind_engine: Annotated[Any, Depends(get_interaction_mind_engine)],
) -> InteractionMindPayload:
    return handle_get_interaction_mind(entity_id, interaction_mind_engine)
