"""Web API for G41 subject evolution mainline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from zentex.nine_questions.subject_evolution_mainline import (
    G41AgendaItem,
    G41CognitiveToolSpec,
    G41MainlineRuntime,
)


router = APIRouter(prefix="/g41", tags=["g41"])


class G41PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_phase: str
    context: dict[str, Any] = Field(default_factory=dict)


class G41AgendaEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: dict[str, Any] = Field(default_factory=dict)


class G41CandidatePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_gap_id: str
    target_component: str
    failure_patterns: list[str]
    proposed_files: list[str] = []
    rollback_conditions: list[str]
    validation_requirements: list[str]


def _runtime(request: Request) -> G41MainlineRuntime:
    runtime = getattr(request.app.state, "subject_evolution_runtime", None)
    if runtime is None:
        runtime = G41MainlineRuntime()
        request.app.state.subject_evolution_runtime = runtime
    return runtime


@router.post("/tools")
def register_tool(payload: G41CognitiveToolSpec, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).register_tool(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "subject_evolution_tool_rejected", "message": str(exc)}) from exc


@router.get("/tools")
def list_tools(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _runtime(request).list_tools()]


@router.get("/tools/{tool_id}")
def get_tool(tool_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).get_tool(tool_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "subject_evolution_tool_not_found"}) from exc


@router.post("/tool-plans")
def build_tool_plan(payload: G41PlanRequest, request: Request) -> dict[str, Any]:
    return _runtime(request).build_invocation_plan(
        context=payload.context,
        target_phase=payload.target_phase,
    ).model_dump(mode="json")


@router.post("/agenda/items")
def add_agenda_item(payload: G41AgendaItem, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).add_agenda_item(payload).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "subject_evolution_agenda_rejected", "message": str(exc)}) from exc


@router.get("/agenda/items")
def list_agenda_items(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _runtime(request).list_agenda()]


@router.post("/agenda/evaluate")
def evaluate_agenda(payload: G41AgendaEvaluationRequest, request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _runtime(request).evaluate_agenda(payload.context)]


@router.post("/candidate-patches")
def create_candidate_patch(payload: G41CandidatePatchRequest, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).create_candidate_patch(payload.model_dump(mode="json")).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "subject_evolution_candidate_patch_rejected", "message": str(exc)},
        ) from exc


@router.get("/candidate-patches/{patch_id}")
def get_candidate_patch(patch_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).get_candidate_patch(patch_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "subject_evolution_candidate_patch_not_found"}) from exc


@router.post("/candidate-patches/{patch_id}/verify")
def verify_candidate_patch(patch_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).verify_candidate_patch(patch_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "subject_evolution_candidate_patch_not_found"}) from exc


@router.get("/audit")
def list_audit(request: Request) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in _runtime(request).list_audit_events()]


@router.get("/brain-organs")
def get_brain_organ_map(request: Request) -> dict[str, Any]:
    return _runtime(request).get_brain_organ_map().model_dump(mode="json")


@router.get("/brain-organs/purity")
def verify_brain_organ_purity(request: Request) -> dict[str, Any]:
    return _runtime(request).verify_brain_organ_purity().model_dump(mode="json")


@router.get("/brain-organs/{organ_id}")
def get_brain_organ(organ_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).get_brain_organ(organ_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "subject_evolution_brain_organ_not_found"}) from exc
