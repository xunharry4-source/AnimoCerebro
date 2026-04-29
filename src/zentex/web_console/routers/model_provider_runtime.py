"""Web API for G28 ModelProvider runtime."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from zentex.foundation.specs.model_provider import ModelProviderError
from zentex.llm.model_provider_runtime import ModelProviderRuntime, ProviderEndpointConfig, classify_provider_error

router = APIRouter(prefix="/model-provider-runtime", tags=["model-provider-runtime"])


class GenerateJSONRequest(BaseModel):
    """Provider generate_json API request."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)
    caller_context: dict[str, Any] = Field(default_factory=dict)


def _runtime(request: Request) -> ModelProviderRuntime:
    runtime = getattr(request.app.state, "model_provider_runtime", None)
    if runtime is None:
        runtime = ModelProviderRuntime()
        request.app.state.model_provider_runtime = runtime
    return runtime


@router.post("/providers")
def register_provider(payload: ProviderEndpointConfig, request: Request) -> dict[str, Any]:
    """Register a real HTTP provider endpoint."""

    try:
        config = _runtime(request).register_provider(payload)
    except ModelProviderError as exc:
        raise HTTPException(status_code=400, detail={"error": classify_provider_error(exc), "message": str(exc)}) from exc
    return config.model_dump(mode="json")


@router.post("/providers/{provider_id}/generate-json")
def generate_json(provider_id: str, payload: GenerateJSONRequest, request: Request) -> dict[str, Any]:
    """Invoke a provider and persist a call record."""

    try:
        record = _runtime(request).generate_json(
            provider_id,
            prompt=payload.prompt,
            context=payload.context,
            caller_context=payload.caller_context,
        )
    except ModelProviderError as exc:
        raise HTTPException(status_code=502, detail={"error": classify_provider_error(exc), "message": str(exc)}) from exc
    return record.model_dump(mode="json")


@router.get("/providers/{provider_id}/health")
def provider_health(provider_id: str, request: Request) -> dict[str, Any]:
    """Return cached provider health."""

    try:
        status = _runtime(request).health_probe(provider_id)
    except ModelProviderError as exc:
        raise HTTPException(status_code=404, detail={"error": classify_provider_error(exc), "message": str(exc)}) from exc
    return status.model_dump(mode="json")


@router.get("/calls")
def list_calls(request: Request) -> list[dict[str, Any]]:
    """Return provider call records."""

    return [row.model_dump(mode="json") for row in _runtime(request).list_calls()]


@router.get("/calls/{call_id}")
def get_call(call_id: str, request: Request) -> dict[str, Any]:
    """Return one provider call record."""

    record = _runtime(request).get_call(call_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"error": "call_not_found"})
    return record.model_dump(mode="json")
