from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from zentex.reflection.nine_question_effectiveness import (
    dependent_questions,
    run_question_reflection,
)
from zentex.web_console.dependencies import (
    get_reflection_service,
    get_runtime,
    get_upgrade_execution_service,
)


router = APIRouter(prefix="/reflections", tags=["nine-question-reflections"])

_VALID_QUESTION_IDS = {f"q{i}" for i in range(1, 10)}
_force_reflection_lock = Lock()


class ForceReflectionRequest(BaseModel):
    include_dependencies: bool = Field(default=True)


@router.post("/{question_id}/force")
def force_reflect_question(
    question_id: str,
    body: ForceReflectionRequest,
    runtime: Any = Depends(get_runtime),
    upgrade_execution_service: Any = Depends(get_upgrade_execution_service),
    reflection_service: Any = Depends(get_reflection_service),
) -> dict[str, Any]:
    qid = str(question_id).strip().lower()
    if qid not in _VALID_QUESTION_IDS:
        raise HTTPException(status_code=400, detail=f"Invalid question_id: {question_id}")

    state = getattr(runtime, "nine_question_state", None)
    if state is None:
        raise HTTPException(status_code=503, detail="NineQuestionState is not available")

    state_payload = state.to_payload() if hasattr(state, "to_payload") else {}

    targets = dependent_questions(qid) if body.include_dependencies else [qid]

    results: list[dict[str, Any]] = []
    with _force_reflection_lock:
        for target_q in targets:
            result = run_question_reflection(
                reflection_service=reflection_service,
                question_id=target_q,
                state_payload=state_payload,
                scope="question_with_dependencies" if body.include_dependencies else "single_question",
                trigger="manual_force",
                upgrade_execution_service=upgrade_execution_service,
            )
            results.append(result)

    return {
        "started": True,
        "question_id": qid,
        "scope": "question_with_dependencies" if body.include_dependencies else "single_question",
        "count": len(results),
        "results": results,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("")
def list_nine_question_reflections(
    q_id: Optional[str] = None,
    limit: int = 50,
    reflection_service: Any = Depends(get_reflection_service),
) -> dict[str, Any]:
    capped = max(1, min(limit, 200))
    filters: dict[str, Any] = {
        "question_scope": "nine_questions",
        "limit": capped,
    }
    if q_id:
        filters["question_id"] = str(q_id).strip().lower()
    reflections = reflection_service.list_reflections(filters=filters)
    items = [record.model_dump(mode="json") for record in reflections]

    return {
        "total": len(items),
        "items": items,
    }


@router.get("/{reflection_id}")
def get_nine_question_reflection(
    reflection_id: str,
    reflection_service: Any = Depends(get_reflection_service),
) -> dict[str, Any]:
    try:
        record = reflection_service.get_reflection(reflection_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail=f"Reflection not found: {reflection_id}")
    if record is None:
        raise HTTPException(status_code=404, detail=f"Reflection not found: {reflection_id}")
    return record.model_dump(mode="json")
