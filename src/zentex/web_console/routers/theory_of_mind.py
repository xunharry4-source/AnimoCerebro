from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from zentex.cognition.theory_of_mind import (
    EntityType,
    InteractionSignal,
    MindModel,
    get_theory_of_mind_engine,
)


router = APIRouter()


class ObservationRequest(BaseModel):
    entity_type: EntityType = EntityType.UNKNOWN
    signals: list[InteractionSignal] = Field(min_length=1)


class CorrectionRequest(BaseModel):
    hypothesis_id: str = Field(min_length=1)
    corrected_intent: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    confirmed: bool = True


def _get_engine(request: Request):
    engine = getattr(request.app.state, "theory_of_mind_engine", None)
    if engine is not None:
        return engine
    engine = get_theory_of_mind_engine()
    request.app.state.theory_of_mind_engine = engine
    return engine


@router.post("/theory-of-mind/entities/{entity_id}/observations")
def observe_entity(entity_id: str, payload: ObservationRequest, request: Request) -> MindModel:
    try:
        return _get_engine(request).observe_entity(
            entity_id=entity_id,
            entity_type=payload.entity_type,
            signals=payload.signals,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/theory-of-mind/entities/{entity_id}")
def get_mind_model(entity_id: str, request: Request) -> MindModel:
    model = _get_engine(request).get_mind_model(entity_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"MindModel {entity_id} not found")
    return model


@router.get("/theory-of-mind/entities")
def list_mind_models(request: Request) -> list[MindModel]:
    return _get_engine(request).list_models()


@router.post("/theory-of-mind/entities/{entity_id}/corrections")
def correct_mind_model(entity_id: str, payload: CorrectionRequest, request: Request) -> MindModel:
    try:
        return _get_engine(request).record_correction(
            entity_id=entity_id,
            hypothesis_id=payload.hypothesis_id,
            corrected_intent=payload.corrected_intent,
            evidence_ref=payload.evidence_ref,
            confirmed=payload.confirmed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
